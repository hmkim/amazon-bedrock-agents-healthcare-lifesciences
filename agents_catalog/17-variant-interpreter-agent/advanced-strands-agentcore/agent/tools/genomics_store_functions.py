"""
Genomics Store Analysis Functions Module
Targeting: genomicsvariantstore, genomicsannotationstore, default database
Using HealthOmics stores directly instead of DynamoDB tracking
"""

import os
import boto3
from botocore.client import Config
import json
from datetime import datetime
import time
import re
import pandas as pd
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError

# PyIceberg for S3 Tables direct access
try:
    from pyiceberg.catalog import load_catalog
    import pyarrow.compute as pc
    PYICEBERG_AVAILABLE = True
except ImportError:
    PYICEBERG_AVAILABLE = False
    print("⚠️ PyIceberg not available - S3 Tables direct access disabled")

# S3 Tables configuration (set via environment variables)
S3TABLES_BUCKET_ARN = os.environ.get('S3TABLES_BUCKET_ARN', '')
S3TABLES_NAMESPACE = os.environ.get('S3TABLES_NAMESPACE', 'variant_db')
S3TABLES_TABLE = os.environ.get('S3TABLES_TABLE', 'genomic_variants')

def get_s3tables_catalog():
    """Get PyIceberg catalog for S3 Tables"""
    if not PYICEBERG_AVAILABLE:
        print("⚠️ PyIceberg not available")
        return None
    try:
        print(f"🔄 Connecting to S3 Tables: {S3TABLES_BUCKET_ARN}")

        # Get credentials from boto3 session (works with ECS task role)
        session = boto3.Session()
        credentials = session.get_credentials()
        frozen_credentials = credentials.get_frozen_credentials()

        region = os.environ.get('AWS_REGION', 'us-east-1')
        catalog_config = {
            "type": "rest",
            "warehouse": S3TABLES_BUCKET_ARN,
            "uri": f"https://s3tables.{region}.amazonaws.com/iceberg",
            "rest.sigv4-enabled": "true",
            "rest.signing-name": "s3tables",
            "rest.signing-region": region,
        }

        # Add explicit credentials if available (for container environments)
        if frozen_credentials.access_key:
            catalog_config["s3.access-key-id"] = frozen_credentials.access_key
            catalog_config["s3.secret-access-key"] = frozen_credentials.secret_key
            if frozen_credentials.token:
                catalog_config["s3.session-token"] = frozen_credentials.token
            print("✅ Using explicit AWS credentials from session")

        catalog = load_catalog("s3tables", **catalog_config)
        print("✅ S3 Tables catalog connected successfully")
        return catalog
    except Exception as e:
        print(f"❌ Error loading S3 Tables catalog: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

def query_s3tables_direct(filter_expr=None, columns=None, limit=None):
    """
    Query S3 Tables directly using PyIceberg (bypasses Athena/Lake Formation)

    Args:
        filter_expr: PyArrow filter expression or None for all data
        columns: List of column names to select, or None for all
        limit: Maximum number of rows to return

    Returns:
        List of dictionaries with query results
    """
    try:
        catalog = get_s3tables_catalog()
        if not catalog:
            return []

        table = catalog.load_table(f"{S3TABLES_NAMESPACE}.{S3TABLES_TABLE}")
        scan = table.scan()
        df = scan.to_arrow()

        # Apply column selection
        if columns:
            df = df.select(columns)

        # Apply filter if provided
        if filter_expr is not None:
            df = df.filter(filter_expr)

        # Apply limit
        if limit:
            df = df.slice(0, limit)

        # Convert to list of dicts
        return df.to_pylist()
    except Exception as e:
        print(f"Error querying S3 Tables: {e}")
        return []

def get_sample_counts_from_s3tables():
    """Get variant counts per sample from S3 Tables - optimized to only scan sample_name column"""
    try:
        import sys
        sys.stdout.flush()
        print("🔄 Getting sample counts from S3 Tables...", flush=True)
        catalog = get_s3tables_catalog()
        if not catalog:
            print("❌ No catalog available", flush=True)
            return {}

        table_id = f"{S3TABLES_NAMESPACE}.{S3TABLES_TABLE}"
        print(f"🔄 Loading table: {table_id}", flush=True)
        table = catalog.load_table(table_id)
        print(f"✅ Table loaded, scanning only sample_name column...", flush=True)

        # Only select sample_name column for efficiency (avoids loading all 25M+ rows of all columns)
        df = table.scan(selected_fields=("sample_name",)).to_arrow()
        print(f"✅ Scan complete, {len(df)} rows", flush=True)

        counts = pc.value_counts(df['sample_name'])
        result = {name: count for name, count in
                zip(counts.field('values').to_pylist(), counts.field('counts').to_pylist())}
        print(f"✅ Found {len(result)} samples: {list(result.keys())}", flush=True)
        return result
    except Exception as e:
        print(f"❌ Error getting sample counts: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {}

def query_variants_by_chromosome_s3tables(chromosome: str, sample_name: str = None, limit: int = 100):
    """Query variants by chromosome from S3 Tables using PyIceberg"""
    try:
        print(f"🔄 Querying variants for chromosome {chromosome}...", flush=True)
        catalog = get_s3tables_catalog()
        if not catalog:
            return {"error": "Could not connect to S3 Tables"}

        table = catalog.load_table(f"{S3TABLES_NAMESPACE}.{S3TABLES_TABLE}")

        # Normalize chromosome format (accept both "17" and "chr17")
        chrom = chromosome if chromosome.startswith("chr") else f"chr{chromosome}"

        # Build filter
        from pyiceberg.expressions import EqualTo, And
        row_filter = EqualTo("chrom", chrom)
        if sample_name:
            row_filter = And(row_filter, EqualTo("sample_name", sample_name))

        print(f"🔄 Scanning for chrom={chrom}, sample={sample_name}, limit={limit}...", flush=True)

        # Query with filter and limit
        df = table.scan(
            row_filter=row_filter,
            selected_fields=("sample_name", "variant_name", "chrom", "pos", "ref", "alt", "qual", "filter", "info"),
            limit=limit
        ).to_arrow()

        print(f"✅ Found {len(df)} variants", flush=True)

        # Convert to list of dicts
        results = []
        for i in range(len(df)):
            row = {
                "sample_name": str(df["sample_name"][i]),
                "variant_name": str(df["variant_name"][i]),
                "chrom": str(df["chrom"][i]),
                "pos": int(df["pos"][i].as_py()),
                "ref": str(df["ref"][i]),
                "alt": df["alt"][i].as_py(),
                "qual": float(df["qual"][i].as_py()) if df["qual"][i].as_py() else None,
                "filter": str(df["filter"][i]),
            }
            # Parse VEP annotation from info
            info_dict = dict(df["info"][i].as_py()) if df["info"][i].as_py() else {}
            if "CSQ" in info_dict:
                row["vep_annotation"] = info_dict["CSQ"][:200] + "..." if len(info_dict.get("CSQ", "")) > 200 else info_dict.get("CSQ", "")
            results.append(row)

        # Get chromosome stats
        chrom_df = table.scan(
            row_filter=row_filter,
            selected_fields=("sample_name",)
        ).to_arrow()
        total_count = len(chrom_df)

        return {
            "analysis_type": f"Chromosome {chromosome} Variants",
            "chromosome": chrom,
            "sample_filter": sample_name,
            "total_variants": total_count,
            "returned_variants": len(results),
            "limit": limit,
            "results": results,
            "source": "s3_tables_pyiceberg"
        }

    except Exception as e:
        print(f"❌ Error querying chromosome variants: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

def query_variants_by_gene_s3tables(gene_symbol: str, sample_name: str = None, limit: int = 50):
    """Query variants by gene symbol from S3 Tables using PyIceberg (searches VEP CSQ annotations)"""
    try:
        print(f"🔄 Querying variants for gene {gene_symbol}...", flush=True)
        catalog = get_s3tables_catalog()
        if not catalog:
            return {"error": "Could not connect to S3 Tables"}

        table = catalog.load_table(f"{S3TABLES_NAMESPACE}.{S3TABLES_TABLE}")

        # Build filter for sample if provided
        from pyiceberg.expressions import EqualTo
        row_filter = EqualTo("sample_name", sample_name) if sample_name else None

        # Scan and filter by gene in VEP annotation (CSQ field in info)
        # Note: PyIceberg doesn't support filtering on map fields, so we need to scan and filter in Python
        print(f"🔄 Scanning variants and filtering for gene {gene_symbol}...", flush=True)

        scan_kwargs = {
            "selected_fields": ("sample_name", "variant_name", "chrom", "pos", "ref", "alt", "qual", "filter", "info"),
            "limit": 10000  # Scan more rows to find gene matches
        }
        if row_filter:
            scan_kwargs["row_filter"] = row_filter

        df = table.scan(**scan_kwargs).to_arrow()

        # Filter by gene in VEP annotation
        gene_upper = gene_symbol.upper()
        results = []
        for i in range(len(df)):
            info_dict = dict(df["info"][i].as_py()) if df["info"][i].as_py() else {}
            csq = info_dict.get("CSQ", "")

            # Check if gene symbol is in the CSQ annotation
            if gene_upper in csq.upper():
                row = {
                    "sample_name": str(df["sample_name"][i]),
                    "variant_name": str(df["variant_name"][i]),
                    "chrom": str(df["chrom"][i]),
                    "pos": int(df["pos"][i].as_py()),
                    "ref": str(df["ref"][i]),
                    "alt": df["alt"][i].as_py(),
                    "qual": float(df["qual"][i].as_py()) if df["qual"][i].as_py() else None,
                    "filter": str(df["filter"][i]),
                    "vep_annotation": csq[:300] + "..." if len(csq) > 300 else csq
                }
                results.append(row)

                if len(results) >= limit:
                    break

        print(f"✅ Found {len(results)} variants for gene {gene_symbol}", flush=True)

        return {
            "analysis_type": f"Gene {gene_symbol} Variants",
            "gene": gene_symbol,
            "sample_filter": sample_name,
            "total_variants_found": len(results),
            "limit": limit,
            "results": results,
            "source": "s3_tables_pyiceberg",
            "note": "Variants filtered by VEP CSQ annotation containing gene symbol"
        }

    except Exception as e:
        print(f"❌ Error querying gene variants: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

def validate_sql_input(value):
    """Validate input to prevent SQL injection - only allow alphanumeric and safe characters"""
    if not isinstance(value, str):
        value = str(value)
    # Allow alphanumeric, underscore, hyphen, and dot
    if not re.match(r'^[a-zA-Z0-9_.-]+$', value):
        raise ValueError(f"Invalid input: {value}. Only alphanumeric characters, underscore, hyphen, and dot are allowed.")
    return value

# === ATHENA S3 TABLES QUERY FUNCTIONS ===
# S3 Tables Athena configuration (set via environment variables)
S3TABLES_CATALOG = os.environ.get('S3TABLES_CATALOG', 's3tablescatalog/genomics-variant-tables')
S3TABLES_DATABASE = os.environ.get('S3TABLES_DATABASE', 'variant_db')
S3TABLES_ATHENA_OUTPUT = os.environ.get('S3TABLES_ATHENA_OUTPUT', '')

def query_s3tables_athena(sql_query: str, timeout_seconds: int = 60):
    """
    Execute an Athena query on S3 Tables using s3tablescatalog.

    Args:
        sql_query: SQL query to execute
        timeout_seconds: Maximum time to wait for query completion

    Returns:
        Dict with query results or error
    """
    try:
        athena = boto3.client('athena', region_name='us-east-1')

        print(f"🔄 Executing Athena query on S3 Tables...", flush=True)
        print(f"   Catalog: {S3TABLES_CATALOG}", flush=True)
        print(f"   Query: {sql_query[:200]}...", flush=True)

        # Start query execution
        response = athena.start_query_execution(
            QueryString=sql_query,
            QueryExecutionContext={
                'Catalog': S3TABLES_CATALOG,
                'Database': S3TABLES_DATABASE
            },
            ResultConfiguration={
                'OutputLocation': S3TABLES_ATHENA_OUTPUT
            },
            WorkGroup='primary'
        )

        query_execution_id = response['QueryExecutionId']
        print(f"   Query ID: {query_execution_id}", flush=True)

        # Wait for query completion
        start_time = time.time()
        while True:
            status_response = athena.get_query_execution(QueryExecutionId=query_execution_id)
            status = status_response['QueryExecution']['Status']['State']

            if status in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
                break

            if time.time() - start_time > timeout_seconds:
                return {"error": f"Query timed out after {timeout_seconds} seconds"}

            time.sleep(1)

        if status == 'FAILED':
            error_message = status_response['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
            return {"error": f"Query failed: {error_message}"}

        if status == 'CANCELLED':
            return {"error": "Query was cancelled"}

        # Get results
        results_response = athena.get_query_results(QueryExecutionId=query_execution_id)

        # Parse results
        columns = []
        rows = []

        result_set = results_response.get('ResultSet', {})
        result_rows = result_set.get('Rows', [])

        if result_rows:
            # First row is headers
            columns = [col.get('VarCharValue', '') for col in result_rows[0].get('Data', [])]

            # Remaining rows are data
            for row in result_rows[1:]:
                row_data = {}
                for i, col in enumerate(row.get('Data', [])):
                    if i < len(columns):
                        row_data[columns[i]] = col.get('VarCharValue', '')
                rows.append(row_data)

        print(f"✅ Query returned {len(rows)} rows", flush=True)

        return {
            "success": True,
            "query_execution_id": query_execution_id,
            "columns": columns,
            "row_count": len(rows),
            "results": rows,
            "source": "athena_s3tables"
        }

    except Exception as e:
        print(f"❌ Athena query error: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

def query_variants_by_chromosome_athena(chromosome: str, sample_name: str = None, limit: int = 100):
    """
    Query variants by chromosome from S3 Tables using Athena.

    Args:
        chromosome: Chromosome identifier (e.g., "17", "chr17")
        sample_name: Optional sample name to filter
        limit: Maximum number of results

    Returns:
        Dict with query results
    """
    # Normalize chromosome format
    chrom = chromosome if chromosome.startswith("chr") else f"chr{chromosome}"

    # Build SQL query
    sql = f"""
    SELECT sample_name, variant_name, chrom, pos, ref, alt, qual, filter, info
    FROM genomic_variants
    WHERE chrom = '{chrom}'
    """

    if sample_name:
        sample_name = validate_sql_input(sample_name)
        sql += f"AND sample_name = '{sample_name}'\n"

    sql += f"ORDER BY pos\nLIMIT {int(limit)}"

    result = query_s3tables_athena(sql)

    if "error" in result:
        return result

    # Also get total count
    count_sql = f"""
    SELECT COUNT(*) as total_count
    FROM genomic_variants
    WHERE chrom = '{chrom}'
    """
    if sample_name:
        count_sql += f"AND sample_name = '{sample_name}'"

    count_result = query_s3tables_athena(count_sql)
    total_count = 0
    if count_result.get("results"):
        total_count = int(count_result["results"][0].get("total_count", 0))

    return {
        "analysis_type": f"Chromosome {chromosome} Variants (Athena)",
        "chromosome": chrom,
        "sample_filter": sample_name,
        "total_variants": total_count,
        "returned_variants": result.get("row_count", 0),
        "limit": limit,
        "results": result.get("results", []),
        "source": "athena_s3tables"
    }

def query_variants_by_gene_athena(gene_symbol: str, sample_name: str = None, limit: int = 50):
    """
    Query variants by gene symbol from S3 Tables using Athena (searches VEP CSQ annotations).

    Args:
        gene_symbol: Gene symbol (e.g., "BRCA1", "TP53")
        sample_name: Optional sample name to filter
        limit: Maximum number of results

    Returns:
        Dict with query results
    """
    gene_symbol = validate_sql_input(gene_symbol)

    # Build SQL query - search for gene in info field (contains CSQ annotation)
    sql = f"""
    SELECT sample_name, variant_name, chrom, pos, ref, alt, qual, filter, info
    FROM genomic_variants
    WHERE info['CSQ'] LIKE '%{gene_symbol.upper()}%'
    """

    if sample_name:
        sample_name = validate_sql_input(sample_name)
        sql += f"AND sample_name = '{sample_name}'\n"

    sql += f"LIMIT {int(limit)}"

    result = query_s3tables_athena(sql)

    if "error" in result:
        return result

    return {
        "analysis_type": f"Gene {gene_symbol} Variants (Athena)",
        "gene": gene_symbol,
        "sample_filter": sample_name,
        "total_variants_found": result.get("row_count", 0),
        "limit": limit,
        "results": result.get("results", []),
        "source": "athena_s3tables",
        "note": "Variants filtered by VEP CSQ annotation containing gene symbol"
    }

def get_sample_summary_athena():
    """Get summary of samples and variant counts using Athena on S3 Tables."""
    sql = """
    SELECT sample_name, COUNT(*) as variant_count
    FROM genomic_variants
    GROUP BY sample_name
    ORDER BY variant_count DESC
    """

    result = query_s3tables_athena(sql)

    if "error" in result:
        return result

    return {
        "analysis_type": "Sample Summary (Athena)",
        "samples": result.get("results", []),
        "total_samples": len(result.get("results", [])),
        "source": "athena_s3tables"
    }

def analyze_allele_frequencies_athena(sample_names: list = None, frequency_threshold: float = 0.01):
    """
    Analyze allele frequencies using Athena on S3 Tables.

    Args:
        sample_names: Optional list of sample names to filter
        frequency_threshold: Frequency threshold for rare variant analysis (default: 0.01 = 1%)

    Returns:
        Dict with frequency analysis results
    """
    # Build SQL query for frequency analysis
    sql = """
    SELECT
        sample_name,
        chrom,
        COUNT(*) as variant_count,
        SUM(CASE WHEN filter = 'PASS' THEN 1 ELSE 0 END) as pass_variants,
        AVG(CAST(qual AS DOUBLE)) as avg_quality
    FROM genomic_variants
    """

    if sample_names and len(sample_names) > 0:
        samples_str = ",".join([f"'{validate_sql_input(s)}'" for s in sample_names])
        sql += f"WHERE sample_name IN ({samples_str})\n"

    sql += """
    GROUP BY sample_name, chrom
    ORDER BY sample_name, chrom
    LIMIT 200
    """

    result = query_s3tables_athena(sql)

    if "error" in result:
        return result

    return {
        "analysis_type": "Allele Frequency Analysis (Athena)",
        "sample_filter": sample_names,
        "frequency_threshold": frequency_threshold,
        "results": result.get("results", []),
        "total_records": result.get("row_count", 0),
        "source": "athena_s3tables",
        "note": "Frequency analysis by chromosome per sample"
    }

def compare_sample_variants_athena(sample_names: list):
    """
    Compare variant profiles between multiple samples using Athena.

    Args:
        sample_names: List of sample names to compare (minimum 2 required)

    Returns:
        Dict with sample comparison results
    """
    if not sample_names or len(sample_names) < 2:
        return {"error": "At least 2 sample names are required for comparison"}

    # Validate sample names
    validated_samples = [validate_sql_input(s) for s in sample_names]
    samples_str = ",".join([f"'{s}'" for s in validated_samples])

    # Query for variant counts per sample
    count_sql = f"""
    SELECT sample_name, COUNT(*) as variant_count
    FROM genomic_variants
    WHERE sample_name IN ({samples_str})
    GROUP BY sample_name
    """

    count_result = query_s3tables_athena(count_sql)

    # Query for chromosome distribution
    chrom_sql = f"""
    SELECT sample_name, chrom, COUNT(*) as variant_count
    FROM genomic_variants
    WHERE sample_name IN ({samples_str})
    GROUP BY sample_name, chrom
    ORDER BY sample_name, variant_count DESC
    LIMIT 100
    """

    chrom_result = query_s3tables_athena(chrom_sql)

    # Query for shared variants (same position)
    shared_sql = f"""
    SELECT chrom, pos, ref, alt, COUNT(DISTINCT sample_name) as sample_count
    FROM genomic_variants
    WHERE sample_name IN ({samples_str})
    GROUP BY chrom, pos, ref, alt
    HAVING COUNT(DISTINCT sample_name) > 1
    LIMIT 50
    """

    shared_result = query_s3tables_athena(shared_sql)

    return {
        "analysis_type": "Sample Comparison Analysis (Athena)",
        "samples_compared": validated_samples,
        "sample_counts": count_result.get("results", []),
        "chromosome_distribution": chrom_result.get("results", []),
        "shared_variants": shared_result.get("results", []),
        "shared_variant_count": shared_result.get("row_count", 0),
        "source": "athena_s3tables"
    }

# Initialize AWS configuration with comprehensive error handling
def get_aws_config():
    """Get AWS configuration with multiple fallback options"""
    region = None
    account_id = None
    
    # Method 1: Environment variables
    region = os.environ.get('AWS_DEFAULT_REGION') or os.environ.get('AWS_REGION') or os.environ.get('REGION')
    
    # Method 2: boto3 session
    if not region:
        try:
            session = boto3.Session()
            region = session.region_name
        except Exception:
            pass
    
    # Method 3: Default region
    if not region:
        region = '<YOUR_REGION>'
        print(f"No region configured, using default: {region}")
    
    # Try to get account ID
    try:
        sts_client = boto3.client('sts', region_name=region)
        account_id = sts_client.get_caller_identity()['Account']
        print(f"✅ AWS configuration detected - Region: {region}, Account: {account_id}")
    except Exception as e:
        print(f"⚠️ Warning: Could not get AWS account info: {e}")
        account_id = os.environ.get('ACCOUNT_ID', '<YOUR_ACCOUNT_ID>')
        print(f"Using default account ID: {account_id}")
    
    return region, account_id

# Get AWS configuration
REGION, ACCOUNT_ID = get_aws_config()

# Environment variables for genomics stores
MODEL_ID = os.environ.get('MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0')
LAKE_FORMATION_DATABASE = os.environ.get('LAKE_FORMATION_DATABASE', '<YOUR_AWS_PROFILE>')
VARIANT_STORE_NAME = os.environ.get('VARIANT_STORE_NAME', 'genomicsvariantstore')
ANNOTATION_STORE_NAME = os.environ.get('ANNOTATION_STORE_NAME', 'genomicsannotationstore')

# Genomic analysis constants
PATHOGENIC_SIGNIFICANCE = ['Pathogenic', 'Likely_pathogenic', 'Pathogenic/Likely_pathogenic']
BENIGN_SIGNIFICANCE = ['Benign', 'Likely_benign', 'Benign/Likely_benign']
HIGH_IMPACT_CONSEQUENCES = ['stop_gained', 'stop_lost', 'start_lost', 'frameshift_variant', 'splice_donor_variant', 'splice_acceptor_variant']
MODERATE_IMPACT_CONSEQUENCES = ['missense_variant', 'inframe_deletion', 'inframe_insertion']

# Bedrock configuration
BEDROCK_CONFIG = Config(connect_timeout=300, read_timeout=300, retries={'max_attempts': 0})

# Initialize clients
def initialize_aws_clients():
    """Initialize AWS clients with error handling"""
    clients = {}
    
    try:
        clients['athena'] = boto3.client('athena', region_name=REGION)
        print("✅ Athena client initialized")
    except Exception as e:
        print(f"⚠️ Athena client failed: {e}")
        clients['athena'] = None
    
    try:
        clients['bedrock'] = boto3.client(service_name='bedrock-runtime', region_name=REGION, config=BEDROCK_CONFIG)
        print("✅ Bedrock client initialized")
    except Exception as e:
        print(f"⚠️ Bedrock client failed: {e}")
        clients['bedrock'] = None
    
    try:
        clients['omics'] = boto3.client('omics', region_name=REGION)
        print("✅ HealthOmics client initialized")
    except Exception as e:
        print(f"⚠️ HealthOmics client failed: {e}")
        clients['omics'] = None
    
    try:
        clients['glue'] = boto3.client('glue', region_name=REGION)
        print("✅ Glue client initialized")
    except Exception as e:
        print(f"⚠️ Glue client failed: {e}")
        clients['glue'] = None
    
    return clients

# Initialize all clients
aws_clients = initialize_aws_clients()
athena_client = aws_clients['athena']
bedrock_client = aws_clients['bedrock']
omics_client = aws_clients['omics']
glue_client = aws_clients['glue']

print(f"Region: {REGION}")
print(f"Account ID: {ACCOUNT_ID}")
print(f"Variant Store: {VARIANT_STORE_NAME}")
print(f"Annotation Store: {ANNOTATION_STORE_NAME}")
print(f"Database: {LAKE_FORMATION_DATABASE}")

# === CORE GENOMIC ANALYSIS FUNCTIONS ===
def get_variant_store_info():
    """
    Get information about the genomicsvariantstore using HealthOmics API
    """
    if omics_client is None:
        return {'error': 'HealthOmics client not available'}
        
    try:
        # Get variant store details
        var_store = omics_client.get_variant_store(name=VARIANT_STORE_NAME)
        
        store_info = {
            'name': var_store['name'],
            'id': var_store['id'],
            'status': var_store['status'],
            'creation_time': var_store.get('creationTime', ''),
            'description': var_store.get('description', ''),
            'reference': var_store.get('reference', {}),
            'sse_config': var_store.get('sseConfig', {}),
            'status_message': var_store.get('statusMessage', ''),
            'store_size_bytes': var_store.get('storeSizeBytes', 0),
            'tags': var_store.get('tags', {})
        }
        
        return {
            'variant_store': store_info,
            'store_type': 'HealthOmics Variant Store'
        }
        
    except Exception as e:
        return {'error': f'Error getting variant store info: {str(e)}'}

def get_annotation_store_info():
    """
    Get information about the genomicsannotationstore using HealthOmics API
    """
    if omics_client is None:
        return {'error': 'HealthOmics client not available'}
        
    try:
        # Get annotation store details
        ann_store = omics_client.get_annotation_store(name=ANNOTATION_STORE_NAME)
        
        store_info = {
            'name': ann_store['name'],
            'id': ann_store['id'],
            'status': ann_store['status'],
            'creation_time': ann_store.get('creationTime', ''),
            'description': ann_store.get('description', ''),
            'store_format': ann_store.get('storeFormat', ''),
            'store_options': ann_store.get('storeOptions', {}),
            'sse_config': ann_store.get('sseConfig', {}),
            'status_message': ann_store.get('statusMessage', ''),
            'store_size_bytes': ann_store.get('storeSizeBytes', 0),
            'tags': ann_store.get('tags', {})
        }
        
        return {
            'annotation_store': store_info,
            'store_type': 'HealthOmics Annotation Store'
        }
        
    except Exception as e:
        return {'error': f'Error getting annotation store info: {str(e)}'}

def execute_athena_query_on_stores(query, database=None):
    """
    Execute Athena query on S3 Tables genomics data
    Uses S3 Tables catalog for querying Iceberg tables
    """
    if athena_client is None:
        raise Exception("Athena client not available. Please configure AWS credentials and region.")

    try:
        if not database:
            database = 'variant_db'

        # S3 Tables bucket name for catalog reference
        s3tables_bucket = 'genomics-variant-tables'
        s3tables_catalog = f's3tablescatalog/{s3tables_bucket}'

        # Transform query to use fully qualified S3 Tables catalog path
        # Replace unqualified table references with S3 Tables catalog path
        modified_query = query
        if 'genomic_variants' in query and s3tables_catalog not in query:
            # Replace simple table reference with fully qualified path
            modified_query = query.replace(
                'genomic_variants',
                f'"{s3tables_catalog}".{database}.genomic_variants'
            )
            modified_query = modified_query.replace(
                'FROM variant_db.',
                f'FROM "{s3tables_catalog}".'
            )

        print(f"Executing query on S3 Tables database '{database}': {query}")

        # Print the query execution details in the expected format
        print("=" * 84)
        print(f"Executing query on S3 Tables catalog '{s3tables_catalog}': ")
        print(f"        {modified_query}")

        response = athena_client.start_query_execution(
            QueryString=modified_query,
            WorkGroup='primary',
            ResultConfiguration={
                'OutputLocation': f's3://genomics-vep-output-{ACCOUNT_ID}-{ACCOUNT_ID}-{REGION}/athena-results/'
            }
        )
        
        query_id = response['QueryExecutionId']
        
        # Wait for completion
        max_attempts = 30
        for attempt in range(max_attempts):
            result = athena_client.get_query_execution(QueryExecutionId=query_id)
            status = result['QueryExecution']['Status']['State']
            
            if status == 'SUCCEEDED':
                break
            elif status in ['FAILED', 'CANCELLED']:
                error_reason = result['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
                raise Exception(f"Query failed: {error_reason}")
            
            time.sleep(2)  # nosemgrep: arbitrary-sleep
        
        if status != 'SUCCEEDED':
            raise Exception("Query timed out")
        
        # Get results with pagination
        rows = []
        next_token = None
        columns = None
        
        while True:
            if next_token:
                results = athena_client.get_query_results(
                    QueryExecutionId=query_id,
                    NextToken=next_token,
                    MaxResults=1000
                )
            else:
                results = athena_client.get_query_results(
                    QueryExecutionId=query_id,
                    MaxResults=1000
                )
            
            # Get column names from first response
            if columns is None:
                columns = [col['Name'] for col in results['ResultSet']['ResultSetMetadata']['ColumnInfo']]
            
            # Process rows (skip header only on first page)
            start_idx = 1 if next_token is None else 0
            for row in results['ResultSet']['Rows'][start_idx:]:
                row_data = [col.get('VarCharValue', '') for col in row['Data']]
                row_dict = dict(zip(columns, row_data))
                rows.append(row_dict)
            
            # Check if there are more results
            next_token = results.get('NextToken')
            if not next_token:
                break
        
        print(f"Retrieved {len(rows)} total rows from Athena query")
        return rows
        
    except Exception as e:
        print(f"Error executing Athena query: {e}")
def get_table_schema_info():
    """
    Get schema information for variant and annotation stores
    """
    try:
        var_store_info = get_variant_store_info()
        ann_store_info = get_annotation_store_info()
        
        # Get actual store names from HealthOmics
        var_store_name = VARIANT_STORE_NAME
        ann_store_name = ANNOTATION_STORE_NAME
        
        # Try to get schema from Glue catalog if available
        variant_schema = "sampleid, contigname, start, end, referenceallele, alternatealleles, filters, annotations, qual, depth, information"
        annotation_schema = "contigname, start, end, referenceallele, alternatealleles, attributes"
        
        if glue_client:
            try:
                # Get variant store schema
                var_response = glue_client.get_table(
                    DatabaseName=LAKE_FORMATION_DATABASE,
                    Name=var_store_name
                )
                variant_columns = [col['Name'] for col in var_response['Table']['StorageDescriptor']['Columns']]
                variant_schema = ", ".join(variant_columns)
            except Exception as e:
                print(f"Could not get variant store schema from Glue: {e}")
            
            try:
                # Get annotation store schema
                ann_response = glue_client.get_table(
                    DatabaseName=LAKE_FORMATION_DATABASE,
                    Name=ann_store_name
                )
                annotation_columns = [col['Name'] for col in ann_response['Table']['StorageDescriptor']['Columns']]
                annotation_schema = ", ".join(annotation_columns)
            except Exception as e:
                print(f"Could not get annotation store schema from Glue: {e}")
        
        annotation_structure = """
VEP Annotations Structure:
- v.annotations.vep[1].symbol (gene symbol)
- v.annotations.vep[1].impact (HIGH, MODERATE, LOW)
- v.annotations.vep[1].consequence[1] (variant consequence)
- v.annotations.vep[1].biotype (gene biotype)
- v.annotations.vep[1].sift_prediction (SIFT score)
- v.annotations.vep[1].polyphen_prediction (PolyPhen score)

ClinVar Attributes Structure:
- a.attributes['CLNSIG'] (clinical significance)
- a.attributes['CLNDN'] (disease name)
- a.attributes['GENEINFO'] (gene information)
- a.attributes['CLNREVSTAT'] (review status)
- a.attributes['RS'] (dbSNP ID)
- a.attributes['ALLELEID'] (ClinVar allele ID)
"""
        
        return {
            'variant_store_name': var_store_name,
            'annotation_store_name': ann_store_name,
            'variant_store_schema': variant_schema,
            'annotation_store_schema': annotation_schema,
            'annotation_structure': annotation_structure
        }
        
    except Exception as e:
        return {'error': f'Error getting schema info: {str(e)}'}

def construct_dynamic_query(user_question, patient_ids=None):
    """
    Construct a dynamic SQL query based on user question and schema information
    """
    try:
        # Get schema information
        schema_info = get_table_schema_info()
        
        if 'error' in schema_info:
            return schema_info
        
        var_store_name = schema_info['variant_store_name']
        ann_store_name = schema_info['annotation_store_name']
        
        # Create a comprehensive prompt for Claude to construct the query
        schema_context = f"""
GENOMIC DATABASE SCHEMA INFORMATION:

VARIANT STORE TABLE: {var_store_name}
Available columns: {schema_info.get('variant_store_schema', 'Schema not available')}

ANNOTATION STORE TABLE: {ann_store_name} 
Available columns: {schema_info.get('annotation_store_schema', 'Schema not available')}

ANNOTATION ATTRIBUTES STRUCTURE:
{schema_info.get('annotation_structure', 'Structure not available')}

COMMON JOIN PATTERN:
The variant and annotation stores are typically joined on:
- REPLACE(v.contigname, 'chr', '') = a.contigname
- v.start = a.start
- v.referenceallele = a.referenceallele
- v.alternatealleles[1] = a.alternatealleles[1]

VEP ANNOTATIONS ACCESS (MUST use cardinality checks):
- VEP gene symbol: CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].symbol END
- VEP impact: CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].impact END
- VEP consequence: CASE WHEN cardinality(v.annotations.vep) > 0 AND cardinality(v.annotations.vep[1].consequence) > 0 THEN v.annotations.vep[1].consequence[1] END
- VEP biotype: CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].biotype END

CLINVAR ATTRIBUTES ACCESS:
- Clinical significance: a.attributes['CLNSIG']
- Disease name: a.attributes['CLNDN']
- Gene info: a.attributes['GENEINFO']
- Review status: a.attributes['CLNREVSTAT']
- dbSNP ID: a.attributes['RS']
- Allele ID: a.attributes['ALLELEID']

COMMON FILTERS:
- Quality variants: v.filters[1] = 'PASS'
- High quality variants: v.qual > 50 AND contains(v.filters, 'PASS')
- Pass only variants: contains(v.filters, 'PASS') AND v.qual > 30
- Pathogenic variants: a.attributes['CLNSIG'] IN ('Pathogenic', 'Likely_pathogenic')
- High impact: CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].impact END = 'HIGH'

CRITICAL SYNTAX RULES:
1. Table references: Use {var_store_name} and {ann_store_name} exactly as shown
2. Join syntax: REPLACE(v.contigname, 'chr', '') = a.contigname (NOT both sides)
3. VEP arrays: ALWAYS use CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].field END
4. Alternatealleles: Use v.alternatealleles[1] for first alternate allele
5. Quality filtering: Always include v.qual > 30 AND contains(v.filters, 'PASS')
6. The 1000 genomes frequency: 1000 genomes frequency available in v.information['af']

USER QUESTION: {user_question}
"""
        
        if patient_ids:
            schema_context += f"\nPATIENT FILTER: Include only these patient IDs: {patient_ids}"
        
        schema_context += """

Please construct a SQL query to answer the user's question using the schema information provided above. 
The query should:
1. Use proper table aliases (v for variant store, a for annotation store)
2. Include appropriate JOINs if both tables are needed
3. Handle array access safely with cardinality checks for VEP annotations
4. Use proper attribute access for ClinVar data
5. Include patient filtering if specified
6. Be optimized for performance

Return ONLY the SQL query without any explanation or markdown formatting.
"""
        
        return {
            'schema_context': schema_context,
            'var_store_name': var_store_name,
            'ann_store_name': ann_store_name,
            'patient_ids': patient_ids
        }
        
    except Exception as e:
        return {"error": f"Error constructing dynamic query: {str(e)}"}

def execute_dynamic_query(user_question, patient_ids=None):
    """
    Execute a dynamically constructed query based on user question
    """
    try:
        # Get query construction context
        query_context = construct_dynamic_query(user_question, patient_ids)
        
        if 'error' in query_context:
            return query_context
        
        # Use bedrock to generate the SQL query
        if bedrock_client is None:
            return {"error": "Bedrock client not available for dynamic query construction"}
        
        prompt = query_context['schema_context']
        
        # Call Claude to generate the SQL query
        response = bedrock_client.invoke_model(
            modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt + "\n\nIMPORTANT: Use LEFT JOIN or INNER JOIN explicitly instead of just JOIN."
                    }
                ]
            })
        )
        
        response_body = json.loads(response['body'].read())
        generated_query = response_body['content'][0]['text'].strip()
        
        # Clean up the query (remove any markdown formatting)
        if generated_query.startswith('```sql'):
            generated_query = generated_query.replace('```sql', '').replace('```', '').strip()
        elif generated_query.startswith('```'):
            generated_query = generated_query.replace('```', '').strip()
        
        # Execute the generated query
        results = execute_athena_query_on_stores(generated_query)
        
        return {
            'user_question': user_question,
            'generated_query': generated_query,
            'results': results,
            'query_context': 'Dynamic query constructed using schema analysis'
        }
        
    except Exception as e:
        return {"error": f"Error executing dynamic query: {str(e)}"}

def format_dynamic_query_results(query_result):
    """
    Format results from dynamic query execution
    """
    if isinstance(query_result, dict) and 'error' in query_result:
        return f"❌ Error: {query_result['error']}"
    
    if 'results' not in query_result:
        return "❌ No results returned from dynamic query"
    
    results = query_result['results']
    user_question = query_result.get('user_question', 'Unknown question')
    generated_query = query_result.get('generated_query', 'Query not available')
    
    formatted_response = f"🔍 Dynamic Query Analysis for: '{user_question}'\n"
    formatted_response += "=" * 60 + "\n\n"
    
    formatted_response += "📋 Generated SQL Query:\n"
    formatted_response += "-" * 30 + "\n"
    formatted_response += f"{generated_query}\n\n"
    
    formatted_response += "📊 Query Results:\n"
    formatted_response += "-" * 30 + "\n"
    
    if isinstance(results, dict) and 'error' in results:
        formatted_response += f"❌ Query execution error: {results['error']}\n"
    elif isinstance(results, list):
        if len(results) == 0:
            formatted_response += "No results found matching your criteria.\n"
        else:
            formatted_response += f"Found {len(results)} results:\n\n"
            # Show first few rows as sample
            sample_size = min(10, len(results))
            for i, row in enumerate(results[:sample_size], 1):
                formatted_response += f"Row {i}: {row}\n"
            if len(results) > sample_size:
                formatted_response += f"\n... and {len(results) - sample_size} more rows"
    else:
        formatted_response += str(results)
    
    return formatted_response

def get_available_samples_from_variant_store():
    """
    Get available samples from S3 Tables genomic_variants table
    Uses PyIceberg for direct access (bypasses Athena/Lake Formation permissions)
    """
    try:
        # Try PyIceberg direct access first (faster and no permission issues)
        if PYICEBERG_AVAILABLE:
            sample_counts = get_sample_counts_from_s3tables()
            if sample_counts:
                samples = []
                for sample_name, count in sorted(sample_counts.items()):
                    samples.append({
                        'sample_id': sample_name,
                        'variant_count': count,
                        'source': 's3_tables_pyiceberg'
                    })

                response_text = f"Available samples in S3 Tables ({len(samples)} total):\n"
                for sample in samples:
                    response_text += f"- {sample['sample_id']}: {sample['variant_count']:,} variants\n"

                return {
                    'analysis_type': 'Available Samples',
                    'results': samples,
                    'summary': response_text,
                    'total_count': len(samples)
                }

        # Fallback to Athena query
        query = """
        SELECT sample_name, COUNT(*) as variant_count
        FROM genomic_variants
        GROUP BY sample_name
        ORDER BY sample_name
        """

        results = execute_athena_query_on_stores(query)

        if not results:
            return {
                'analysis_type': 'Available Samples',
                'results': [],
                'summary': 'No samples found in S3 Tables.'
            }

        samples = []
        for row in results:
            samples.append({
                'sample_id': row['sample_name'],
                'variant_count': int(row['variant_count']),
                'source': 's3_tables'
            })

        response_text = f"Available samples in S3 Tables ({len(samples)} total):\n"
        for sample in samples:
            response_text += f"- {sample['sample_id']}: {sample['variant_count']:,} variants\n"

        return {
            'analysis_type': 'Available Samples',
            'results': samples,
            'summary': response_text,
            'total_count': len(samples)
        }

    except Exception as e:
        return {'error': f'Error getting samples from S3 Tables: {str(e)}'}


# === MAIN ANALYSIS FUNCTIONS FOR GENOMICS STORES ===
def get_stores_information():
    """
    Get comprehensive information about variant and annotation stores
    """
    try:
        variant_info = get_variant_store_info()
        annotation_info = get_annotation_store_info()
        
        response_text = f"Genomics Stores Information:\n\n"
        
        # Variant Store Info
        response_text += f"Variant Store ({VARIANT_STORE_NAME}):\n"
        if 'error' in variant_info:
            response_text += f"  Error: {variant_info['error']}\n"
        else:
            store = variant_info.get('variant_store', {})
            response_text += f"  - ID: {store.get('id', 'N/A')}\n"
            response_text += f"  - Status: {store.get('status', 'N/A')}\n"
            response_text += f"  - Created: {store.get('creation_time', 'N/A')}\n"
            response_text += f"  - Description: {store.get('description', 'N/A')}\n"
            response_text += f"  - Size: {store.get('store_size_bytes', 0):,} bytes\n"
        
        # Annotation Store Info
        response_text += f"\nAnnotation Store ({ANNOTATION_STORE_NAME}):\n"
        if 'error' in annotation_info:
            response_text += f"  Error: {annotation_info['error']}\n"
        else:
            store = annotation_info.get('annotation_store', {})
            response_text += f"  - ID: {store.get('id', 'N/A')}\n"
            response_text += f"  - Status: {store.get('status', 'N/A')}\n"
            response_text += f"  - Format: {store.get('store_format', 'N/A')}\n"
            response_text += f"  - Created: {store.get('creation_time', 'N/A')}\n"
            response_text += f"  - Size: {store.get('store_size_bytes', 0):,} bytes\n"
        
        return {
            'analysis_type': 'Stores Information',
            'variant_store_info': variant_info,
            'annotation_store_info': annotation_info,
            'summary': response_text
        }
        
    except Exception as e:
        return {
            'analysis_type': 'Stores Information',
            'error': f"Error getting stores information: {str(e)}",
            'summary': f"Failed to retrieve stores information: {str(e)}"
        }

def query_variants_by_gene_function(gene_symbols, sample_ids=None, include_frequency=True):
    """Query variants in specific genes with comprehensive clinical annotations"""
    try:
        genes = [g.strip().upper() for g in gene_symbols if g.strip()]
        # Validate gene symbols
        validated_genes = [validate_sql_input(gene.strip()) for gene in genes if gene.strip()]
        if not validated_genes:
            return {"error": "No valid gene symbols provided"}
        
        gene_list = "', '".join(validated_genes)
        
        sample_filter = ""
        if sample_ids:
            validated_samples = [validate_sql_input(s.strip()) for s in sample_ids if s.strip()]
            if validated_samples:
                sample_list = "', '".join(validated_samples)
                sample_filter = f"AND v.sampleid IN ('{sample_list}')"
        
        frequency_fields = ""
        if include_frequency:
            frequency_fields = "v.information['af'] as allele_frequency_1000g,"
        
        # Validate store names
        validated_variant_store = validate_sql_input(VARIANT_STORE_NAME)
        validated_annotation_store = validate_sql_input(ANNOTATION_STORE_NAME)
        
        query = f"""
        WITH variant_annotations AS (
            SELECT 
                v.sampleid,
                v.contigname,
                v.start,
                v.referenceallele,
                v.alternatealleles[1] as alternate_allele,
                v.qual,
                v.depth,
                {frequency_fields}
                v.filters[1] as filter_status,
                
                CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].symbol END as vep_gene,
                CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].impact END as vep_impact,
                CASE WHEN cardinality(v.annotations.vep) > 0 AND cardinality(v.annotations.vep[1].consequence) > 0 
                     THEN v.annotations.vep[1].consequence[1] END as vep_consequence,
                
                a.attributes['CLNSIG'] as clinvar_significance,
                a.attributes['CLNDN'] as associated_disease,
                split_part(a.attributes['GENEINFO'], ':', 1) as clinvar_gene
                
            FROM {validated_variant_store} v
            LEFT JOIN {validated_annotation_store} a ON (
                REPLACE(v.contigname, 'chr', '') = REPLACE(a.contigname, 'chr', '')
                AND v.start = a.start
                AND v.referenceallele = a.referenceallele
                AND v.alternatealleles[1] = a.alternatealleles[1]
            )
            WHERE v.qual > 30 
                AND contains(v.filters, 'PASS')
                AND (
                    (cardinality(v.annotations.vep) > 0 AND UPPER(v.annotations.vep[1].symbol) IN ('{gene_list}'))
                    OR UPPER(split_part(a.attributes['GENEINFO'], ':', 1)) IN ('{gene_list}')
                )
                {sample_filter}
        )
        
        SELECT 
            sampleid,
            CONCAT(contigname, ':', CAST(start as VARCHAR), ':', referenceallele, '>', alternate_allele) as variant_id,
            COALESCE(clinvar_gene, vep_gene) as gene_symbol,
            vep_consequence as consequence,
            vep_impact as impact,
            clinvar_significance,
            associated_disease,
            qual,
            depth,
            {'allele_frequency_1000g,' if include_frequency else ''}
            
            CASE 
                WHEN clinvar_significance = 'Pathogenic' AND vep_impact = 'HIGH' THEN 10
                WHEN clinvar_significance = 'Pathogenic' AND vep_impact = 'MODERATE' THEN 9
                WHEN clinvar_significance = 'Likely_pathogenic' AND vep_impact = 'HIGH' THEN 8
                WHEN clinvar_significance = 'Likely_pathogenic' AND vep_impact = 'MODERATE' THEN 7
                WHEN clinvar_significance = 'Uncertain_significance' AND vep_impact = 'HIGH' THEN 6
                WHEN vep_impact = 'HIGH' THEN 5
                WHEN clinvar_significance = 'Uncertain_significance' AND vep_impact = 'MODERATE' THEN 4
                ELSE 1
            END as priority_score

        FROM variant_annotations
        ORDER BY priority_score DESC, qual DESC
        """
        
        results = execute_athena_query_on_stores(query)
        
        gene_counts = {}
        impact_counts = {}
        significance_counts = {}
        
        for row in results:
            gene = row.get('gene_symbol', 'Unknown')
            impact = row.get('impact', 'Unknown')
            significance = row.get('clinvar_significance', 'Unknown')
            
            gene_counts[gene] = gene_counts.get(gene, 0) + 1
            if impact != 'Unknown':
                impact_counts[impact] = impact_counts.get(impact, 0) + 1
            if significance != 'Unknown':
                significance_counts[significance] = significance_counts.get(significance, 0) + 1
        
        return {
            "analysis_type": "Gene-Specific Variant Analysis",
            "genes_queried": genes,
            "total_variants": len(results),
            "variants": results[:100],
            "summary": {
                "variants_per_gene": gene_counts,
                "impact_distribution": impact_counts,
                "clinical_significance": significance_counts
            }
        }
        
    except Exception as e:
        return {"error": f"Error in gene variant query: {str(e)}"}

def query_variants_by_chromosome_function(chromosome, sample_ids=None, position_range=None):
    """Query variants by chromosome with optional position range filtering"""
    try:
        # Validate chromosome input
        chr_clean = validate_sql_input(chromosome.replace('chr', '').upper())
        
        sample_filter = ""
        if sample_ids:
            validated_samples = [validate_sql_input(s.strip()) for s in sample_ids if s.strip()]
            if validated_samples:
                sample_list = "', '".join(validated_samples)
                sample_filter = f"AND v.sampleid IN ('{sample_list}')"
        
        position_filter = ""
        if position_range and '-' in position_range:
            try:
                start_pos, end_pos = position_range.split('-')
                position_filter = f"AND v.start BETWEEN {int(start_pos)} AND {int(end_pos)}"
            except ValueError:
                return {"error": "Invalid position range format. Use 'start-end' format."}
        
        query = f"""
        SELECT 
            v.sampleid,
            v.contigname,
            v.start,
            v.referenceallele,
            v.alternatealleles[1] as alternate_allele,
            v.qual,
            v.depth,
            v.information['af'] as allele_frequency_1000g,
            
            CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].symbol END as gene_symbol,
            CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].impact END as impact,
            CASE WHEN cardinality(v.annotations.vep) > 0 AND cardinality(v.annotations.vep[1].consequence) > 0 
                 THEN v.annotations.vep[1].consequence[1] END as consequence,
            
            a.attributes['CLNSIG'] as clinical_significance,
            a.attributes['CLNDN'] as associated_disease
            
        FROM {validate_sql_input(VARIANT_STORE_NAME)} v
        LEFT JOIN {validate_sql_input(ANNOTATION_STORE_NAME)} a ON (
            REPLACE(v.contigname, 'chr', '') = REPLACE(a.contigname, 'chr', '')
            AND v.start = a.start
            AND v.referenceallele = a.referenceallele
            AND v.alternatealleles[1] = a.alternatealleles[1]
        )
        WHERE v.qual > 30 
            AND contains(v.filters, 'PASS')
            AND REPLACE(v.contigname, 'chr', '') = '{chr_clean}'
            {position_filter}
            {sample_filter}
        ORDER BY v.start
        """
        
        results = execute_athena_query_on_stores(query)
        
        gene_counts = {}
        impact_counts = {}
        
        for row in results:
            gene = row.get('gene_symbol')
            impact = row.get('impact')
            
            if gene:
                gene_counts[gene] = gene_counts.get(gene, 0) + 1
            if impact:
                impact_counts[impact] = impact_counts.get(impact, 0) + 1
        
        return {
            "analysis_type": "Chromosome-Specific Analysis",
            "chromosome": chr_clean,
            "position_range": position_range if position_range else "entire chromosome",
            "total_variants": len(results),
            "variants": results[:100],
            "summary": {
                "top_genes": dict(sorted(gene_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
                "impact_distribution": impact_counts
            }
        }
        
    except Exception as e:
        return {"error": f"Error in chromosome variant query: {str(e)}"}

def analyze_allele_frequencies_function(sample_ids=None, frequency_threshold=0.01):
    """Analyze allele frequencies and compare with 1000 Genomes Project data"""
    try:
        sample_filter = ""
        if sample_ids:
            samples = [s.strip() for s in sample_ids if s.strip()]
            if samples:
                sample_list = "', '".join(samples)
                sample_filter = f"AND v.sampleid IN ('{sample_list}')"
        
        query = f"""
        WITH variant_data AS (
            SELECT 
                v.sampleid,
                v.contigname,
                v.start,
                v.referenceallele,
                v.alternatealleles[1] as alternate_allele,
                v.qual,
                v.depth,
                
                CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].symbol END as vep_gene,
                CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].impact END as vep_impact,
                CASE WHEN cardinality(v.annotations.vep) > 0 AND cardinality(v.annotations.vep[1].consequence) > 0 
                     THEN v.annotations.vep[1].consequence[1] END as vep_consequence,
                
                a.attributes['CLNSIG'] as clinical_significance,
                split_part(a.attributes['GENEINFO'], ':', 1) as clinvar_gene,
                
                TRY_CAST(v.information['af'] as DOUBLE) as allele_frequency,
                TRY_CAST(v.information['dp'] as INTEGER) as total_depth,
                TRY_CAST(v.information['mq'] as DOUBLE) as mapping_quality
                
            FROM {validate_sql_input(VARIANT_STORE_NAME)} v
            LEFT JOIN {validate_sql_input(ANNOTATION_STORE_NAME)} a ON (
                REPLACE(v.contigname, 'chr', '') = REPLACE(a.contigname, 'chr', '')
                AND v.start = a.start
                AND v.referenceallele = a.referenceallele
                AND v.alternatealleles[1] = a.alternatealleles[1]
            )
            WHERE v.information['af'] IS NOT NULL
                AND v.qual > 30 
                AND contains(v.filters, 'PASS')
                {sample_filter}
        )

        SELECT 
            sampleid,
            COALESCE(clinvar_gene, vep_gene) as gene_symbol,
            contigname,
            start,
            referenceallele,
            alternate_allele,
            qual,
            depth,
            allele_frequency,
            total_depth,
            mapping_quality,
            clinical_significance,
            vep_impact,
            vep_consequence as consequence,
            
            CASE 
                WHEN qual > 100 AND depth > 20 THEN 'High Quality'
                WHEN qual > 50 AND depth > 10 THEN 'Medium Quality'
                ELSE 'Low Quality'
            END as quality_tier,
            
            CASE 
                WHEN allele_frequency < 0.001 THEN 'Very Rare'
                WHEN allele_frequency < {frequency_threshold} THEN 'Rare'
                WHEN allele_frequency < 0.05 THEN 'Uncommon'
                WHEN allele_frequency IS NOT NULL THEN 'Common'
                ELSE 'Unknown'
            END as rarity_category,
            
            CASE 
                WHEN allele_frequency IS NOT NULL AND allele_frequency > 0 
                THEN ROUND(-LOG10(allele_frequency), 2)
                ELSE NULL
            END as rarity_score,
            
            CASE 
                WHEN allele_frequency IS NOT NULL AND allele_frequency > 0 AND allele_frequency < 1
                THEN ROUND(2 * allele_frequency * (1 - allele_frequency), 4)
                ELSE NULL
            END as expected_het_frequency

        FROM variant_data
        WHERE allele_frequency IS NOT NULL
        ORDER BY allele_frequency ASC, qual DESC
        """
        
        results = execute_athena_query_on_stores(query)
        
        rarity_counts = {}
        quality_counts = {}
        rare_variants = []
        
        for row in results:
            rarity = row.get('rarity_category', 'Unknown')
            quality = row.get('quality_tier', 'Unknown')
            
            rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1
            quality_counts[quality] = quality_counts.get(quality, 0) + 1
            
            if rarity in ['Very Rare', 'Rare']:
                rare_variants.append(row)
        
        return {
            "analysis_type": "Allele Frequency Analysis",
            "frequency_threshold": frequency_threshold,
            "total_variants_with_frequency": len(results),
            "rarity_distribution": rarity_counts,
            "quality_distribution": quality_counts,
            "rare_variants_detail": rare_variants[:50],
            "summary_statistics": {
                "very_rare_count": rarity_counts.get('Very Rare', 0),
                "rare_count": rarity_counts.get('Rare', 0),
                "high_quality_count": quality_counts.get('High Quality', 0)
            }
        }
        
    except Exception as e:
        return {"error": f"Error in allele frequency analysis: {str(e)}"}

def compare_sample_variants_function(sample_ids):
    """Compare variant profiles between multiple samples for population analysis"""
    try:
        validated_samples = [validate_sql_input(s.strip()) for s in sample_ids if s.strip()]
        if len(validated_samples) < 2:
            return {"error": "At least 2 sample IDs required for comparison"}
        
        sample_list = "', '".join(validated_samples)
        
        query = f"""
        WITH sample_variants AS (
            SELECT 
                v.sampleid,
                v.qual,
                v.depth,
                v.referenceallele,
                v.alternatealleles[1] as alternate_allele,
                v.filters[1] as filter_status,
                
                CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].symbol END as vep_gene,
                CASE WHEN cardinality(v.annotations.vep) > 0 THEN v.annotations.vep[1].impact END as vep_impact,
                
                a.attributes['CLNSIG'] as clinical_significance,
                split_part(a.attributes['GENEINFO'], ':', 1) as clinvar_gene
                
            FROM {validate_sql_input(VARIANT_STORE_NAME)} v
            LEFT JOIN {validate_sql_input(ANNOTATION_STORE_NAME)} a ON (
                REPLACE(v.contigname, 'chr', '') = REPLACE(a.contigname, 'chr', '')
                AND v.start = a.start
                AND v.referenceallele = a.referenceallele
                AND v.alternatealleles[1] = a.alternatealleles[1]
            )
            WHERE v.filters[1] = 'PASS'
                AND v.sampleid IN ('{sample_list}')
        )

        SELECT 
            sampleid,
            COUNT(*) as total_variants,
            
            COUNT(CASE WHEN clinical_significance = 'Pathogenic' THEN 1 END) as pathogenic_count,
            COUNT(CASE WHEN clinical_significance = 'Likely_pathogenic' THEN 1 END) as likely_pathogenic_count,
            COUNT(CASE WHEN clinical_significance = 'Uncertain_significance' THEN 1 END) as vus_count,
            COUNT(CASE WHEN clinical_significance IN ('Benign', 'Likely_benign') THEN 1 END) as benign_count,
            
            COUNT(CASE WHEN vep_impact = 'HIGH' THEN 1 END) as high_impact_count,
            COUNT(CASE WHEN vep_impact = 'MODERATE' THEN 1 END) as moderate_impact_count,
            COUNT(CASE WHEN vep_impact = 'LOW' THEN 1 END) as low_impact_count,
            COUNT(CASE WHEN vep_impact = 'MODIFIER' THEN 1 END) as modifier_impact_count,
            
            ROUND(AVG(CAST(qual as DOUBLE)), 2) as avg_quality,
            ROUND(AVG(CAST(depth as DOUBLE)), 2) as avg_depth,
            MIN(qual) as min_quality,
            MAX(qual) as max_quality,
            
            COUNT(DISTINCT COALESCE(clinvar_gene, vep_gene)) as unique_genes_affected,
            
            COUNT(CASE 
                WHEN LENGTH(referenceallele) = 1 AND LENGTH(alternate_allele) = 1 
                THEN 1 
            END) as snv_count,
            
            COUNT(CASE 
                WHEN LENGTH(referenceallele) > LENGTH(alternate_allele) 
                THEN 1 
            END) as deletion_count,
            
            COUNT(CASE 
                WHEN LENGTH(referenceallele) < LENGTH(alternate_allele) 
                THEN 1 
            END) as insertion_count,
            
            ROUND(
                COUNT(CASE WHEN clinical_significance IN ('Pathogenic', 'Likely_pathogenic') THEN 1 END) * 100.0 / COUNT(*), 
                2
            ) as pathogenic_percentage

        FROM sample_variants
        GROUP BY sampleid
        ORDER BY sampleid
        """
        
        results = execute_athena_query_on_stores(query)
        
        return {
            "analysis_type": "Sample Comparison Analysis",
            "samples_compared": samples,
            "comparison_results": results,
            "summary": {
                "total_samples": len(results),
                "comparison_metrics": [
                    "total_variants", "pathogenic_count", "high_impact_count", 
                    "avg_quality", "unique_genes_affected", "pathogenic_percentage"
                ]
            }
        }
        
    except Exception as e:
        return {"error": f"Error in sample comparison: {str(e)}"}
