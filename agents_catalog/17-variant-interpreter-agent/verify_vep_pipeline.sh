#!/bin/bash
# VEP Pipeline Verification Script

# Configuration variables (use environment variables or defaults)
ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
REGION="${AWS_REGION:-us-east-1}"
INPUT_BUCKET="${INPUT_BUCKET:-genomics-vcf-input-${ACCOUNT_ID}-${ACCOUNT_ID}-${REGION}}"
OUTPUT_BUCKET="${OUTPUT_BUCKET:-genomics-vep-output-${ACCOUNT_ID}-${ACCOUNT_ID}-${REGION}}"
TEST_VCF="${TEST_VCF:-NA21137.hard-filtered.vcf.gz}"

echo "=========================================="
echo "VEP Pipeline Verification Started"
echo "=========================================="

# Step 1: Upload test VCF file
echo ""
echo "📤 Step 1: Uploading VCF file..."
aws s3 cp s3://1000genomes-dragen/data/dragen-3.5.7b/hg38_altaware_nohla-cnv-anchored/NA21137/$TEST_VCF \
  s3://$INPUT_BUCKET/$TEST_VCF \
  --region $REGION

if [ $? -eq 0 ]; then
    echo "✅ VCF file upload complete"
else
    echo "❌ VCF file upload failed"
    exit 1
fi

# Step 2: Check Lambda function execution (CloudWatch Logs)
echo ""
echo "⏳ Step 2: Waiting for Lambda function execution (10 seconds)..."
sleep 10

echo ""
echo "📋 Checking Lambda logs:"
aws logs tail /aws/lambda/genomics-vep-pipeline-vcf-processor \
  --since 2m \
  --format short \
  --region $REGION | grep -E "(START|END|ERROR|Processing|workflow)" | tail -20

# Step 3: Check HealthOmics workflow execution
echo ""
echo "🔬 Step 3: Checking HealthOmics workflow execution..."
RUNS=$(aws omics list-runs \
  --region $REGION \
  --max-results 5 \
  --query 'items[?contains(name, `NA21137`)].{Id:id,Name:name,Status:status,StartTime:startTime}' \
  --output table)

if [ -z "$RUNS" ]; then
    echo "⚠️  Workflow execution has not started yet"
else
    echo "$RUNS"
fi

# Step 4: Check DynamoDB tracking table
echo ""
echo "📊 Step 4: Checking DynamoDB tracking table..."
aws dynamodb scan \
  --table-name genomics-vep-pipeline-tracking \
  --filter-expression "contains(sample_id, :sample)" \
  --expression-attribute-values '{":sample":{"S":"NA21137"}}' \
  --region $REGION \
  --query 'Items[0].{SampleID:sample_id.S,Status:status.S,WorkflowID:workflow_run_id.S,Timestamp:timestamp.S}' \
  --output table

echo ""
echo "=========================================="
echo "✅ Pipeline Verification Complete"
echo "=========================================="
echo ""
echo "Use the following command to continue monitoring workflow status:"
echo "aws omics list-runs --region $REGION --max-results 5"
