#!/usr/bin/env python3
"""
Create S3 Tables (Iceberg) for genomic variant data storage
Replaces HealthOmics Variant Store functionality
"""

import os
import boto3
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.table.sorting import SortOrder, SortField, SortDirection, NullOrder
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import IdentityTransform, BucketTransform
from pyiceberg.types import (
    NestedField, StringType, LongType, DoubleType, 
    MapType, BooleanType, ListType
)

# Configuration (from environment variables)
REGION = os.environ.get('AWS_REGION', 'us-east-1')
ACCOUNT_ID = os.environ.get('AWS_ACCOUNT_ID', '')
TABLE_BUCKET_NAME = os.environ.get('TABLE_BUCKET_NAME', 'genomics-variant-tables')
NAMESPACE = os.environ.get('S3TABLES_NAMESPACE', 'variant_db')
TABLE_NAME = os.environ.get('S3TABLES_TABLE', 'genomic_variants')

def create_s3_table_bucket():
    """Create S3 Table Bucket"""
    s3_client = boto3.client('s3', region_name=REGION)
    s3tables_client = boto3.client('s3tables', region_name=REGION)
    
    try:
        response = s3tables_client.create_table_bucket(
            name=TABLE_BUCKET_NAME
        )
        bucket_arn = response['arn']
        print(f"✅ Created S3 Table Bucket: {bucket_arn}")
        return bucket_arn
    except s3tables_client.exceptions.ConflictException:
        # Bucket already exists
        response = s3tables_client.list_table_buckets()
        for bucket in response.get('tableBuckets', []):
            if bucket['name'] == TABLE_BUCKET_NAME:
                print(f"✅ S3 Table Bucket already exists: {bucket['arn']}")
                return bucket['arn']
    except Exception as e:
        print(f"❌ Error creating table bucket: {e}")
        raise

def load_s3_tables_catalog(bucket_arn: str):
    """Load S3 Tables catalog"""
    catalog_config = {
        "type": "rest",
        "warehouse": bucket_arn,
        "uri": f"https://s3tables.{REGION}.amazonaws.com/iceberg",
        "rest.sigv4-enabled": "true",
        "rest.signing-name": "s3tables",
        "rest.signing-region": REGION
    }
    return load_catalog("s3tables", **catalog_config)

def create_genomic_variants_table(catalog, namespace: str, table_name: str):
    """Create Iceberg table for genomic variants"""
    
    # Schema matching VCF structure with VEP annotations
    schema = Schema(
        NestedField(1, "sample_name", StringType(), required=True),
        NestedField(2, "variant_name", StringType(), required=True, doc="ID field from VCF"),
        NestedField(3, "chrom", StringType(), required=True),
        NestedField(4, "pos", LongType(), required=True),
        NestedField(5, "ref", StringType(), required=True),
        NestedField(6, "alt", ListType(element_id=1000, element_type=StringType(), element_required=True), required=True),
        NestedField(7, "qual", DoubleType()),
        NestedField(8, "filter", StringType()),
        NestedField(9, "genotype", StringType()),
        NestedField(10, "info", MapType(key_type=StringType(), key_id=1001, value_type=StringType(), value_id=1002)),
        NestedField(11, "attributes", MapType(key_type=StringType(), key_id=2001, value_type=StringType(), value_id=2002)),
        NestedField(12, "is_reference_block", BooleanType(), doc="Used in GVCF for non-variant sites"),
        identifier_field_ids=[1, 2, 3, 4]
    )
    
    # Partition by sample (bucketed) and chromosome
    partition_spec = PartitionSpec(
        PartitionField(source_id=1, field_id=1001, transform=BucketTransform(128), name="sample_bucket"),
        PartitionField(source_id=3, field_id=1002, transform=IdentityTransform(), name="chrom")
    )
    
    # Sort by chromosome and position
    sort_order = SortOrder(
        SortField(source_id=3, transform=IdentityTransform(), direction=SortDirection.ASC, null_order=NullOrder.NULLS_LAST),
        SortField(source_id=4, transform=IdentityTransform(), direction=SortDirection.ASC, null_order=NullOrder.NULLS_LAST)
    )
    
    # Create namespace if not exists
    try:
        catalog.create_namespace(namespace)
        print(f"✅ Created namespace: {namespace}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"✅ Namespace {namespace} already exists")
        else:
            raise
    
    # Create table
    try:
        if catalog.table_exists(f"{namespace}.{table_name}"):
            print(f"✅ Table {namespace}.{table_name} already exists")
            return catalog.load_table(f"{namespace}.{table_name}")
        
        table = catalog.create_table(
            identifier=f"{namespace}.{table_name}",
            schema=schema,
            partition_spec=partition_spec,
            sort_order=sort_order,
            properties={"format-version": "2", "write.parquet.compression-codec": "zstd"}
        )
        print(f"✅ Created table: {namespace}.{table_name}")
        return table
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        raise

def main():
    print("🚀 Creating S3 Tables for Genomic Variants")
    print(f"Region: {REGION}")
    print(f"Account: {ACCOUNT_ID}")
    
    # Step 1: Create S3 Table Bucket
    bucket_arn = create_s3_table_bucket()
    
    # Step 2: Load catalog
    print("\n📚 Loading S3 Tables catalog...")
    catalog = load_s3_tables_catalog(bucket_arn)
    
    # Step 3: Create table
    print("\n📊 Creating genomic variants table...")
    table = create_genomic_variants_table(catalog, NAMESPACE, TABLE_NAME)
    
    print("\n✅ Setup complete!")
    print(f"Table Bucket ARN: {bucket_arn}")
    print(f"Table: {NAMESPACE}.{TABLE_NAME}")
    
    return {
        'bucket_arn': bucket_arn,
        'namespace': NAMESPACE,
        'table_name': TABLE_NAME,
        'full_table_name': f"{NAMESPACE}.{TABLE_NAME}"
    }

if __name__ == "__main__":
    result = main()
    print(f"\n📋 Configuration for Notebook:")
    print(f"TABLE_BUCKET_ARN = '{result['bucket_arn']}'")
    print(f"NAMESPACE = '{result['namespace']}'")
    print(f"TABLE_NAME = '{result['table_name']}'")
