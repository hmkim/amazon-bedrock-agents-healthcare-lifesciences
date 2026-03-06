#!/usr/bin/env python3
"""
Test S3 Tables integration with genomics agent
Uses PyIceberg for direct S3 Tables access

Required environment variables:
  - S3TABLES_BUCKET_ARN: ARN of the S3 Tables bucket (e.g., arn:aws:s3tables:us-east-1:<ACCOUNT_ID>:bucket/genomics-variant-tables)
  - AWS_REGION: AWS region (default: us-east-1)
"""
import os
import sys

# Set region (use environment variable or default)
region = os.environ.get('AWS_REGION', 'us-east-1')
os.environ['AWS_DEFAULT_REGION'] = region
os.environ['AWS_REGION'] = region
os.environ['REGION'] = region

# Add agent tools to path
script_dir = os.path.dirname(os.path.abspath(__file__))
tools_path = os.path.join(script_dir, 'advanced-strands-agentcore/agent/tools')
sys.path.insert(0, tools_path)

from genomics_store_functions import (
    get_available_samples_from_variant_store,
    get_sample_counts_from_s3tables,
    get_s3tables_catalog,
    S3TABLES_NAMESPACE,
    S3TABLES_TABLE
)
import pyarrow.compute as pc

print("=" * 80)
print("Testing S3 Tables Integration (PyIceberg)")
print("=" * 80)

# Test 1: List available samples
print("\n📊 Test 1: Get Available Samples")
print("-" * 80)
result = get_available_samples_from_variant_store()
print(result.get('summary', result))

# Test 2: Count total variants (using PyIceberg)
print("\n📊 Test 2: Count Total Variants")
print("-" * 80)
sample_counts = get_sample_counts_from_s3tables()
total = sum(sample_counts.values())
print(f"Total variants: {total:,}")

# Test 3: Sample chromosome distribution (using PyIceberg)
print("\n📊 Test 3: Chromosome Distribution for NA21135")
print("-" * 80)
catalog = get_s3tables_catalog()
if catalog:
    table = catalog.load_table(f"{S3TABLES_NAMESPACE}.{S3TABLES_TABLE}")
    df = table.scan().to_arrow()
    na21135_df = df.filter(pc.equal(df['sample_name'], 'NA21135'))
    chrom_counts = pc.value_counts(na21135_df['chrom'])
    sorted_chroms = sorted(
        zip(chrom_counts.field('values').to_pylist(), chrom_counts.field('counts').to_pylist()),
        key=lambda x: (len(x[0]), x[0])
    )[:10]
    for chrom, count in sorted_chroms:
        print(f"  {chrom}: {count:,} variants")

# Test 4: Query specific variant info
print("\n📊 Test 4: Sample Variant Details (first 5)")
print("-" * 80)
if catalog:
    table = catalog.load_table(f"{S3TABLES_NAMESPACE}.{S3TABLES_TABLE}")
    df = table.scan(limit=5).to_arrow()
    for row in df.to_pylist():
        print(f"  {row['sample_name']}: {row['chrom']}:{row['pos']} {row['ref']}>{row['alt']}")

print("\n" + "=" * 80)
print("✅ All Tests Complete")
print("=" * 80)
