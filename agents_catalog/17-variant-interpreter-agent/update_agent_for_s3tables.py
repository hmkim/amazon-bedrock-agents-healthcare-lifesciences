#!/usr/bin/env python3
"""
Update genomics agent to use S3 Tables instead of Variant Store

Required environment variables:
  - S3TABLES_BUCKET_ARN: ARN of the S3 Tables bucket
  - AWS_REGION: AWS region (default: us-east-1)
"""
import os

# Update configuration (from environment variables)
S3_TABLES_CONFIG = {
    'TABLE_BUCKET_ARN': os.environ.get('S3TABLES_BUCKET_ARN', ''),
    'CATALOG_NAME': os.environ.get('S3TABLES_CATALOG', 's3tables::genomics-variant-tables'),
    'DATABASE': os.environ.get('S3TABLES_DATABASE', 'variant_db'),
    'TABLE': os.environ.get('S3TABLES_TABLE', 'genomic_variants')
}

# Updated Athena query function
def query_s3_tables(query_string, database='variant_db'):
    """Execute Athena query against S3 Tables"""
    import boto3
    import time
    
    region = os.environ.get('AWS_REGION', 'us-east-1')
    athena_output = os.environ.get('S3TABLES_ATHENA_OUTPUT', '')
    catalog = os.environ.get('S3TABLES_CATALOG', 's3tables::genomics-variant-tables')

    athena = boto3.client('athena', region_name=region)

    response = athena.start_query_execution(
        QueryString=query_string,
        QueryExecutionContext={
            'Database': database,
            'Catalog': catalog
        },
        ResultConfiguration={
            'OutputLocation': athena_output
        }
    )
    
    query_id = response['QueryExecutionId']
    
    # Wait for completion
    while True:
        result = athena.get_query_execution(QueryExecutionId=query_id)
        state = result['QueryExecution']['Status']['State']
        
        if state == 'SUCCEEDED':
            break
        elif state in ['FAILED', 'CANCELLED']:
            raise Exception(f"Query failed: {result['QueryExecution']['Status'].get('StateChangeReason')}")
        
        time.sleep(1)
    
    # Get results
    results = athena.get_query_results(QueryExecutionId=query_id)
    return results

# Example queries for S3 Tables
EXAMPLE_QUERIES = {
    'list_patients': """
        SELECT DISTINCT sample_name 
        FROM genomic_variants
    """,
    
    'count_variants': """
        SELECT sample_name, COUNT(*) as variant_count
        FROM genomic_variants
        GROUP BY sample_name
    """,
    
    'chromosome_variants': """
        SELECT * FROM genomic_variants
        WHERE sample_name = '{sample}' AND chrom = '{chromosome}'
        LIMIT 100
    """,
    
    'high_quality_variants': """
        SELECT * FROM genomic_variants
        WHERE sample_name = '{sample}' 
        AND qual > 30 
        AND filter = 'PASS'
        LIMIT 100
    """
}

print("✅ S3 Tables configuration ready")
print(f"Catalog: {S3_TABLES_CONFIG['CATALOG_NAME']}")
print(f"Database: {S3_TABLES_CONFIG['DATABASE']}")
print(f"Table: {S3_TABLES_CONFIG['TABLE']}")
