#!/usr/bin/env python3
"""
VCF to S3 Tables ETL - Processes VCF files and loads into Iceberg tables
Replaces HealthOmics Variant Store import functionality
"""

import boto3
import gzip
from pyiceberg.catalog import load_catalog
from pyiceberg.table import Table
import pyarrow as pa
import pyarrow.parquet as pq
from typing import Dict, List, Any
import re

REGION = 'us-east-1'

def parse_vcf_line(line: str, sample_name: str) -> Dict[str, Any]:
    """Parse single VCF line into dict"""
    fields = line.strip().split('\t')
    
    chrom, pos, variant_id, ref, alt, qual, filt, info = fields[:8]
    genotype = fields[9] if len(fields) > 9 else None
    
    # Parse INFO field
    info_dict = {}
    for item in info.split(';'):
        if '=' in item:
            k, v = item.split('=', 1)
            info_dict[k] = v
        else:
            info_dict[item] = 'true'
    
    return {
        'sample_name': sample_name,
        'variant_name': variant_id if variant_id != '.' else f"{chrom}:{pos}:{ref}:{alt}",
        'chrom': chrom,
        'pos': int(pos),
        'ref': ref,
        'alt': alt.split(','),
        'qual': float(qual) if qual != '.' else None,
        'filter': filt,
        'genotype': genotype,
        'info': info_dict,
        'attributes': {},
        'is_reference_block': False
    }

def process_vcf_to_table(s3_vcf_path: str, table: Table, sample_name: str = None):
    """Process VCF from S3 and append to Iceberg table"""

    # Parse S3 path
    match = re.match(r's3://([^/]+)/(.+)', s3_vcf_path)
    bucket, key = match.groups()

    # Get bucket region for cross-region access
    s3_global = boto3.client('s3')
    try:
        bucket_location = s3_global.get_bucket_location(Bucket=bucket)
        bucket_region = bucket_location['LocationConstraint'] or 'us-east-1'
    except:
        bucket_region = 'us-east-1'

    s3 = boto3.client('s3', region_name=bucket_region)
    print(f"📍 Source bucket region: {bucket_region}")
    
    # Extract sample name from filename if not provided
    if not sample_name:
        sample_name = key.split('/')[-1].split('.')[0]
    
    print(f"📥 Processing VCF: {s3_vcf_path}")
    print(f"👤 Sample: {sample_name}")
    
    # Download and parse VCF
    obj = s3.get_object(Bucket=bucket, Key=key)
    
    variants = []
    with gzip.open(obj['Body'], 'rt') as f:
        for line in f:
            if line.startswith('#'):
                continue
            variants.append(parse_vcf_line(line, sample_name))
            
            # Batch write every 10000 variants
            if len(variants) >= 10000:
                write_batch_to_table(table, variants)
                variants = []
    
    # Write remaining variants
    if variants:
        write_batch_to_table(table, variants)
    
    print(f"✅ Processed {sample_name}")

def write_batch_to_table(table: Table, variants: List[Dict]):
    """Write batch of variants to Iceberg table"""
    
    # Convert to PyArrow with required fields marked as not null
    schema = pa.schema([
        pa.field('sample_name', pa.string(), nullable=False),
        pa.field('variant_name', pa.string(), nullable=False),
        pa.field('chrom', pa.string(), nullable=False),
        pa.field('pos', pa.int64(), nullable=False),
        pa.field('ref', pa.string(), nullable=False),
        pa.field('alt', pa.list_(pa.field('element', pa.string(), nullable=False)), nullable=False),
        pa.field('qual', pa.float64()),
        pa.field('filter', pa.string()),
        pa.field('genotype', pa.string()),
        pa.field('info', pa.map_(pa.string(), pa.field('value', pa.string(), nullable=False))),
        pa.field('attributes', pa.map_(pa.string(), pa.field('value', pa.string(), nullable=False))),
        pa.field('is_reference_block', pa.bool_())
    ])
    
    batch = pa.RecordBatch.from_pylist(variants, schema=schema)
    arrow_table = pa.Table.from_batches([batch])
    table.append(arrow_table)
    print(f"  ✅ Wrote {len(variants)} variants")

def main():
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python vcf_to_s3_tables.py <bucket_arn> <namespace.table> <s3_vcf_path> [sample_name]")
        sys.exit(1)
    
    bucket_arn = sys.argv[1]
    table_id = sys.argv[2]
    vcf_path = sys.argv[3]
    sample_name = sys.argv[4] if len(sys.argv) > 4 else None
    
    # Load catalog and table
    catalog_config = {
        "type": "rest",
        "warehouse": bucket_arn,
        "uri": f"https://s3tables.{REGION}.amazonaws.com/iceberg",
        "rest.sigv4-enabled": "true",
        "rest.signing-name": "s3tables",
        "rest.signing-region": REGION
    }
    catalog = load_catalog("s3tables", **catalog_config)
    table = catalog.load_table(table_id)
    
    # Process VCF
    process_vcf_to_table(vcf_path, table, sample_name)

if __name__ == "__main__":
    main()
