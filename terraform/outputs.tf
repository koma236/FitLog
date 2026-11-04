output "vpc_id" {
  value = aws_vpc.foundation.id
}

output "public_subnet_ids" {
  value = { for key, subnet in aws_subnet.public : key => subnet.id }
}

output "database_subnet_ids" {
  value = { for key, subnet in aws_subnet.database : key => subnet.id }
}

output "security_group_ids" {
  value = { for key, group in aws_security_group.boundary : key => group.id }
}

output "buckets" {
  value = { for key, bucket in aws_s3_bucket.private : key => { name = bucket.bucket, arn = bucket.arn } }
}

output "backend_repository" {
  value = { url = aws_ecr_repository.backend.repository_url, arn = aws_ecr_repository.backend.arn }
}

output "backend_log_group" {
  value = aws_cloudwatch_log_group.backend.name
}

output "role_arns" {
  value = { for key, role in aws_iam_role.ecs : key => role.arn }
}
