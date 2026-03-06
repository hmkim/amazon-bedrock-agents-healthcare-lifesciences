#!/bin/bash
set -e

# Configuration variables (use environment variables or defaults)
ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
REGION="${AWS_REGION:-us-east-1}"
CLINVAR_BUCKET="${CLINVAR_BUCKET:-genomics-clinvar-${ACCOUNT_ID}}"

echo "=== ClinVar Data Setup Started ==="

# Create S3 bucket
echo "1. Creating S3 bucket..."
aws s3 mb s3://${CLINVAR_BUCKET} --region ${REGION} || echo "Bucket already exists."

# Download ClinVar
echo "2. Downloading ClinVar VCF file..."
if [ ! -f "clinvar_20251221.vcf.gz" ]; then
    wget https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar_20251221.vcf.gz
else
    echo "ClinVar file already exists."
fi

# Upload to S3
echo "3. Uploading to S3..."
aws s3 cp clinvar_20251221.vcf.gz s3://${CLINVAR_BUCKET}/clinvar20251221/ --region ${REGION}

echo "=== ClinVar Data Setup Complete ==="
echo "URI: s3://${CLINVAR_BUCKET}/clinvar20251221/clinvar_20251221.vcf.gz"
