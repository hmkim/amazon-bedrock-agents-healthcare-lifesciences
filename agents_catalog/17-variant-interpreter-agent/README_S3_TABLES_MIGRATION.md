# S3 Tables Migration Guide

## Overview
HealthOmics Variant Store is deprecated for new customers (effective Nov 7, 2025). This guide shows how to migrate to S3 Tables (Iceberg format).

## Prerequisites

```bash
pip install pyiceberg pyarrow boto3
```

## Step 1: Create S3 Tables Infrastructure

```bash
python create_s3_tables_for_variants.py
```

This creates:
- S3 Table Bucket: `genomics-variant-tables`
- Namespace: `variant_db`
- Table: `genomic_variants` with schema matching VCF structure

## Step 2: Load VCF Data

```bash
# Single VCF file
python vcf_to_s3_tables.py \
  "arn:aws:s3tables:us-east-1:<ACCOUNT_ID>:bucket/genomics-variant-tables" \
  "variant_db.genomic_variants" \
  "s3://genomics-vcf-input-<ACCOUNT_ID>-<ACCOUNT_ID>-us-east-1/NA21135.hard-filtered.vcf.gz" \
  "NA21135"

# Multiple files
for vcf in s3://your-bucket/*.vcf.gz; do
  python vcf_to_s3_tables.py <bucket_arn> variant_db.genomic_variants "$vcf"
done
```

## Step 3: Query with Athena

```sql
-- List all samples
SELECT DISTINCT sample_name FROM variant_db.genomic_variants;

-- Variants on chromosome 17
SELECT * FROM variant_db.genomic_variants 
WHERE chrom = 'chr17' AND sample_name = 'NA21135';

-- High quality variants
SELECT * FROM variant_db.genomic_variants 
WHERE qual > 30 AND filter = 'PASS';
```

## Step 4: Update Lambda Function

Replace HealthOmics Variant Store calls with S3 Tables writes:

```python
from pyiceberg.catalog import load_catalog

catalog = load_catalog("s3tables", **config)
table = catalog.load_table("variant_db.genomic_variants")

# Append variants
table.append(pyarrow_batch)
```

## Architecture Changes

**Before (Variant Store):**
```
VCF → HealthOmics Import Job → Variant Store → Analytics → Athena
```

**After (S3 Tables):**
```
VCF → Lambda/Batch ETL → S3 Tables (Iceberg) → Athena
```

## Benefits

- **No service limits**: Unlimited storage and tables
- **Standard Iceberg**: Compatible with Spark, Trino, Flink
- **Cost effective**: Pay only for S3 storage
- **Full control**: Custom ETL and schema evolution

## Notes

- Existing Variant Stores continue to work until deprecation
- S3 Tables support ACID transactions and time travel
- Use partitioning (sample, chromosome) for query performance
- Consider AWS Glue or Batch for large-scale ETL
