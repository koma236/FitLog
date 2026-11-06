# B6 runner must start before application secret versions exist. Never reuse the
# Web task/execution roles for administrator access or secret writes.
resource "aws_iam_role" "bootstrap" {
  name               = "${var.environment_name}-bootstrap"
  assume_role_policy = aws_iam_role.ecs["task"].assume_role_policy
}

resource "aws_iam_role" "bootstrap_execution" {
  name               = "${var.environment_name}-bootstrap-exec"
  assume_role_policy = aws_iam_role.ecs["execution"].assume_role_policy
}

resource "aws_cloudwatch_log_group" "bootstrap" {
  name              = "/fitlog/${var.environment_name}/bootstrap"
  retention_in_days = 7
}

resource "aws_iam_role_policy" "bootstrap" {
  name = "initialization-only"
  role = aws_iam_role.bootstrap.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "Identity", Effect = "Allow", Action = ["sts:GetCallerIdentity"], Resource = ["*"] },
      # ELB Describe* and ECS DescribeTaskDefinition have no resource-level
      # authorization. Regional metadata is read-only; the CLI binds all IDs/tags.
      { Sid = "DescribeRegional", Effect = "Allow", Action = ["ecs:DescribeTaskDefinition", "elasticloadbalancing:DescribeLoadBalancers", "elasticloadbalancing:DescribeTags"], Resource = ["*"] },
      { Sid = "Database", Effect = "Allow", Action = ["rds:DescribeDBInstances"], Resource = ["arn:aws:rds:ap-northeast-1:${var.expected_account_id}:db:${var.environment_name}"] },
      { Sid = "Service", Effect = "Allow", Action = ["ecs:DescribeServices"], Resource = ["arn:aws:ecs:ap-northeast-1:${var.expected_account_id}:service/${var.environment_name}/${var.environment_name}-backend"] },
      { Sid = "Distribution", Effect = "Allow", Action = ["cloudfront:GetDistribution", "cloudfront:ListTagsForResource"], Resource = [aws_cloudfront_distribution.edge.arn] },
      { Sid = "Application", Effect = "Allow", Action = ["secretsmanager:DescribeSecret", "secretsmanager:ListSecretVersionIds", "secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"], Resource = [aws_secretsmanager_secret.application.arn] },
      { Sid = "Administrator", Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [one(aws_db_instance.runtime.master_user_secret).secret_arn] },
    ]
  })
}

resource "aws_iam_role_policy" "bootstrap_execution" {
  name = "bootstrap-startup"
  role = aws_iam_role.bootstrap_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "RegistryToken", Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = ["*"] },
      { Sid = "BackendImage", Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = [aws_ecr_repository.backend.arn] },
      { Sid = "BootstrapLogs", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["${aws_cloudwatch_log_group.bootstrap.arn}:*"] },
    ]
  })
}

resource "aws_ecs_task_definition" "bootstrap" {
  family                   = "${var.environment_name}-bootstrap"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "1024"
  task_role_arn            = aws_iam_role.bootstrap.arn
  execution_role_arn       = aws_iam_role.bootstrap_execution.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name        = "backend"
    essential   = true
    image       = "${aws_ecr_repository.backend.repository_url}@${var.backend_image_digest}"
    command     = ["python", "-m", "operations.bootstrap", "--help"]
    environment = [{ name = "AWS_REGION", value = "ap-northeast-1" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.bootstrap.name
        awslogs-region        = "ap-northeast-1"
        awslogs-stream-prefix = "bootstrap"
        mode                  = "non-blocking"
        max-buffer-size       = "4m"
      }
    }
  }])
  depends_on = [aws_iam_role_policy.bootstrap, aws_iam_role_policy.bootstrap_execution]
}

output "bootstrap_runner" {
  description = "Metadata only; no task is launched by Terraform."
  value = {
    task_definition = aws_ecs_task_definition.bootstrap.arn
    log_group       = aws_cloudwatch_log_group.bootstrap.name
    role_arn        = aws_iam_role.bootstrap.arn
    execution_role  = aws_iam_role.bootstrap_execution.arn
  }
}
