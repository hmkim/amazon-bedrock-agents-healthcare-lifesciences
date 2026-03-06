#!/bin/bash
set -e

# Configuration variables (use environment variables or defaults)
ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
REGION="${AWS_REGION:-us-east-1}"
VEP_CACHE_BUCKET="${VEP_CACHE_BUCKET:-genomics-vep-cache-${ACCOUNT_ID}}"

echo "=== VEP Cache Setup Started ==="

# Create S3 bucket
echo "1. Creating S3 bucket..."
aws s3 mb s3://${VEP_CACHE_BUCKET} --region ${REGION} || echo "Bucket already exists."

# Download VEP Cache
echo "2. Downloading VEP Cache file (~20GB, this may take a while)..."
if [ ! -f "homo_sapiens_vep_111_GRCh38.tar.gz" ]; then
    curl -O https://ftp.ensembl.org/pub/release-111/variation/indexed_vep_cache/homo_sapiens_vep_111_GRCh38.tar.gz
else
    echo "Cache file already exists."
fi

# Upload to S3
echo "3. Uploading to S3..."
aws s3 cp homo_sapiens_vep_111_GRCh38.tar.gz s3://${VEP_CACHE_BUCKET}/cache/ --region ${REGION}

# Extract and upload (optional)
echo "4. Extract and sync (optional, takes a long time)..."
read -p "Do you want to extract and upload individual files? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    tar xzf homo_sapiens_vep_111_GRCh38.tar.gz
    aws s3 sync homo_sapiens_vep_111_GRCh38/ s3://${VEP_CACHE_BUCKET}/cache/homo_sapiens_vep_111_GRCh38/ --region ${REGION}
fi

echo "=== VEP Cache Setup Complete ==="
echo "Bucket: s3://${VEP_CACHE_BUCKET}/cache/"
