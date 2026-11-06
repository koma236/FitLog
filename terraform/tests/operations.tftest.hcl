mock_provider "aws" {
  override_during = plan
  source          = "./tests/mocks"
}

variables {
  backend_image_digest         = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  backend_source_revision      = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  postgres_engine_version      = "17.6"
  db_final_snapshot_identifier = "fitlog-demo-test-final-fixture"
  origin_verify_secret         = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  expected_account_id          = "123456789012"
  environment_name             = "fitlog-demo-test"
  availability_zones           = ["ap-northeast-1a", "ap-northeast-1c"]
}

override_resource {
  override_during = plan
  target          = aws_iam_role.bootstrap
  values          = { arn = "arn:aws:iam::123456789012:role/fitlog-demo-test-bootstrap" }
}
override_resource {
  override_during = plan
  target          = aws_iam_role.bootstrap_execution
  values          = { arn = "arn:aws:iam::123456789012:role/fitlog-demo-test-bootstrap-exec" }
}

run "bootstrap_is_separate_and_has_no_startup_secrets" {
  command = plan
  assert {
    condition = (
      aws_ecs_task_definition.bootstrap.family == "fitlog-demo-test-bootstrap" &&
      aws_ecs_task_definition.bootstrap.task_role_arn == aws_iam_role.bootstrap.arn &&
      aws_ecs_task_definition.bootstrap.execution_role_arn == aws_iam_role.bootstrap_execution.arn &&
      !contains(keys(jsondecode(aws_ecs_task_definition.bootstrap.container_definitions)[0]), "secrets") &&
      jsondecode(aws_ecs_task_definition.bootstrap.container_definitions)[0].command == ["python", "-m", "operations.bootstrap", "--help"] &&
      aws_ecs_service.backend.desired_count == 0 &&
      aws_db_instance.runtime.deletion_protection
    )
    error_message = "Bootstrap must start before app secrets exist, without changing Web privileges/defaults."
  }
  assert {
    condition = jsondecode(aws_iam_role_policy.bootstrap.policy).Statement == [
      { Sid = "Identity", Effect = "Allow", Action = ["sts:GetCallerIdentity"], Resource = ["*"] },
      { Sid = "DescribeRegional", Effect = "Allow", Action = ["ecs:DescribeTaskDefinition", "elasticloadbalancing:DescribeLoadBalancers", "elasticloadbalancing:DescribeTags"], Resource = ["*"] },
      { Sid = "Database", Effect = "Allow", Action = ["rds:DescribeDBInstances"], Resource = ["arn:aws:rds:ap-northeast-1:123456789012:db:fitlog-demo-test"] },
      { Sid = "Service", Effect = "Allow", Action = ["ecs:DescribeServices"], Resource = ["arn:aws:ecs:ap-northeast-1:123456789012:service/fitlog-demo-test/fitlog-demo-test-backend"] },
      { Sid = "Distribution", Effect = "Allow", Action = ["cloudfront:GetDistribution", "cloudfront:ListTagsForResource"], Resource = [aws_cloudfront_distribution.edge.arn] },
      { Sid = "Application", Effect = "Allow", Action = ["secretsmanager:DescribeSecret", "secretsmanager:ListSecretVersionIds", "secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"], Resource = [aws_secretsmanager_secret.application.arn] },
      { Sid = "Administrator", Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [one(aws_db_instance.runtime.master_user_secret).secret_arn] },
    ]
    error_message = "Bootstrap permissions must equal the B6 CLI contract, with no Web role changes."
  }
}

run "explicit_teardown_is_possible_after_stop" {
  command = plan
  variables { allow_database_teardown = true }
  assert {
    condition     = !aws_db_instance.runtime.deletion_protection && !aws_db_instance.runtime.skip_final_snapshot && !aws_db_instance.runtime.delete_automated_backups
    error_message = "Only deletion protection is relaxed; final snapshot and backups remain."
  }
}

run "teardown_rejects_running_service" {
  command = plan
  variables {
    allow_database_teardown = true
    enable_backend_service  = true
  }
  expect_failures = [var.allow_database_teardown]
}
