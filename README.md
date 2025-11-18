Repository: ragline-infrastructure
Prerequisite (input variables) 
# VPC, 2 public subnets, 2 private subnets

start with ALB today! 

ragline-infrastructure/
├── management-api-backend/ # ECS service for your ragline API + Dynamo, security groups
├── ingestion-document-processing/ # ECS task + S3 + EventBridge + IAM, security groups
└── README.md

Key Components for Your Pipeline:

modules/api-backend/:
- ECS service for your current ragline API
- ALB, target groups, security groups
- Auto-scaling policies