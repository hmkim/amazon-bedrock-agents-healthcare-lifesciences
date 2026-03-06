#!/bin/bash
set -e

# Configuration variables (use environment variables or defaults)
ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
REGION="${AWS_REGION:-us-east-1}"
ECR_REPO_NAME="${ECR_REPO_NAME:-ensemblorg}"
VEP_VERSION="${VEP_VERSION:-release_113.4}"
VEP_TAG="${VEP_TAG:-113.4}"

echo "=== VEP Docker Image Setup Started ==="

# ECR login
echo "1. Logging into ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Create ECR repository
echo "2. Creating ECR repository..."
aws ecr create-repository --repository-name ${ECR_REPO_NAME} --region ${REGION} 2>/dev/null || echo "Repository already exists."

# Pull VEP Docker image
echo "3. Downloading VEP Docker image..."
docker pull ensemblorg/ensembl-vep:${VEP_VERSION}

# Tag image
echo "4. Tagging image..."
docker tag ensemblorg/ensembl-vep:${VEP_VERSION} ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}:${VEP_TAG}

# Push to ECR
echo "5. Pushing image to ECR..."
docker push ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}:${VEP_TAG}

echo "=== VEP Docker Image Setup Complete ==="
echo "Image URI: ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}:${VEP_TAG}"
