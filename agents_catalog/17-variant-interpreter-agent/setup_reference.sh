#!/bin/bash
set -e

# Configuration variables (use environment variables or defaults)
ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
REGION="${AWS_REGION:-us-east-1}"

echo "=== Reference Genome Setup Started ==="

# Create Reference Store
echo "1. Creating HealthOmics Reference Store..."
REFERENCE_STORE_ID=$(aws omics create-reference-store \
    --name "genomics-reference-store" \
    --description "Reference store for genomic analysis" \
    --region ${REGION} \
    --query 'id' --output text 2>/dev/null || \
    aws omics list-reference-stores --region ${REGION} --query 'referenceStores[0].id' --output text)

echo "Reference Store ID: ${REFERENCE_STORE_ID}"

# Download Reference FASTA
echo "2. Downloading reference genome (~3GB)..."
if [ ! -f "hg38_alt_aware_nohla.fa" ]; then
    aws s3 cp s3://1000genomes-dragen/reference/hg38_alt_aware_nohla.fa . --no-sign-request
else
    echo "Reference file already exists."
fi

# Upload to S3 (temporary bucket required)
TEMP_BUCKET="genomics-reference-temp-${ACCOUNT_ID}"
echo "3. Creating temporary S3 bucket and uploading..."
aws s3 mb s3://${TEMP_BUCKET} --region ${REGION} || echo "Bucket already exists."
aws s3 cp hg38_alt_aware_nohla.fa s3://${TEMP_BUCKET}/reference/ --region ${REGION}

# Import to HealthOmics (IAM Role required)
echo "4. Starting HealthOmics Reference Import..."
echo "Note: IAM Role is required. Run this after CloudFormation deployment."
echo ""
echo "Run the following command after CloudFormation deployment:"
echo "aws omics start-reference-import-job \\"
echo "    --reference-store-id ${REFERENCE_STORE_ID} \\"
echo "    --role-arn arn:aws:iam::${ACCOUNT_ID}:role/GenomicsHealthOmicsRole \\"
echo "    --sources sourceFile=s3://${TEMP_BUCKET}/reference/hg38_alt_aware_nohla.fa,name=GRCh38,description='Human reference genome' \\"
echo "    --region ${REGION}"

echo "=== Reference Genome Setup Complete ==="
