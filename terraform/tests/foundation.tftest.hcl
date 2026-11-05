mock_provider "aws" {
  override_during = plan
  source          = "./tests/mocks"
}

variables {
  origin_verify_secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  expected_account_id  = "123456789012"
  environment_name     = "fitlog-demo-test"
  availability_zones   = ["ap-northeast-1a", "ap-northeast-1c"]
}

# Only provider-computed identifiers are fixtures. Policies and rules stay real.
override_resource {
  override_during = plan
  target          = aws_vpc.foundation
  values          = { id = "vpc-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_internet_gateway.public
  values          = { id = "igw-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_security_group.boundary["ingress"]
  values          = { id = "sg-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_security_group.boundary["app"]
  values          = { id = "sg-00000000000000002" }
}
override_resource {
  override_during = plan
  target          = aws_security_group.boundary["database"]
  values          = { id = "sg-00000000000000003" }
}
override_resource {
  override_during = plan
  target          = aws_s3_bucket.private["static"]
  values          = { id = "fitlog-demo-test-static-123456789012-ap-northeast-1", arn = "arn:aws:s3:::fitlog-demo-test-static-123456789012-ap-northeast-1" }
}
override_resource {
  override_during = plan
  target          = aws_s3_bucket.private["media"]
  values          = { id = "fitlog-demo-test-media-123456789012-ap-northeast-1", arn = "arn:aws:s3:::fitlog-demo-test-media-123456789012-ap-northeast-1" }
}
override_resource {
  override_during = plan
  target          = aws_ecr_repository.backend
  values          = { arn = "arn:aws:ecr:ap-northeast-1:123456789012:repository/fitlog-demo-test/backend" }
}
override_resource {
  override_during = plan
  target          = aws_cloudwatch_log_group.backend
  values          = { arn = "arn:aws:logs:ap-northeast-1:123456789012:log-group:/fitlog/fitlog-demo-test/backend" }
}

override_resource {
  override_during = plan
  target          = aws_iam_role.ecs["task"]
  values          = { id = "fitlog-demo-test-task" }
}
override_resource {
  override_during = plan
  target          = aws_iam_role.ecs["execution"]
  values          = { id = "fitlog-demo-test-execution" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_ingress_rule.connection["app"]
  values          = { security_group_rule_id = "sgr-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_ingress_rule.connection["database"]
  values          = { security_group_rule_id = "sgr-00000000000000002" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_egress_rule.connection["ingress"]
  values          = { security_group_rule_id = "sgr-00000000000000003" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_egress_rule.connection["app"]
  values          = { security_group_rule_id = "sgr-00000000000000004" }
}
override_resource {
  override_during = plan
  target          = aws_vpc_security_group_egress_rule.https
  values          = { security_group_rule_id = "sgr-00000000000000005" }
}

override_resource {
  override_during = plan
  target          = aws_subnet.public["0"]
  values          = { id = "subnet-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_subnet.public["1"]
  values          = { id = "subnet-00000000000000002" }
}
override_resource {
  override_during = plan
  target          = aws_subnet.database["0"]
  values          = { id = "subnet-00000000000000003" }
}
override_resource {
  override_during = plan
  target          = aws_subnet.database["1"]
  values          = { id = "subnet-00000000000000004" }
}
override_resource {
  override_during = plan
  target          = aws_route_table.public
  values          = { id = "rtb-00000000000000001" }
}
override_resource {
  override_during = plan
  target          = aws_route_table.database
  values          = { id = "rtb-00000000000000002" }
}

override_resource {
  override_during = plan
  target          = aws_vpc_security_group_ingress_rule.cloudfront
  values          = { security_group_rule_id = "sgr-00000000000000006" }
}

run "closed_network_and_private_artifacts" {
  command = plan

  assert {
    condition = (
      aws_route_table_association.public["0"].subnet_id == "subnet-00000000000000001" &&
      aws_route_table_association.public["1"].subnet_id == "subnet-00000000000000002" &&
      aws_route_table_association.database["0"].subnet_id == "subnet-00000000000000003" &&
      aws_route_table_association.database["1"].subnet_id == "subnet-00000000000000004" &&
      alltrue([for r in aws_route_table_association.public : r.route_table_id == "rtb-00000000000000001"]) &&
      alltrue([for r in aws_route_table_association.database : r.route_table_id == "rtb-00000000000000002"]) &&
      aws_internet_gateway.public.vpc_id == "vpc-00000000000000001" &&
      aws_route_table.public.vpc_id == "vpc-00000000000000001" &&
      aws_route_table.database.vpc_id == "vpc-00000000000000001" &&
      alltrue([for g in aws_security_group.boundary : g.vpc_id == "vpc-00000000000000001"])
    )
    error_message = "Private subnets must actually use the isolated route table, and all network components must belong to the dedicated VPC."
  }

  assert {
    condition     = aws_vpc.foundation.cidr_block == "10.42.0.0/16" && aws_vpc.foundation.enable_dns_support && aws_vpc.foundation.enable_dns_hostnames
    error_message = "Dedicated VPC requires the approved CIDR and working DNS."
  }
  assert {
    condition = length(aws_subnet.public) == 2 && length(aws_subnet.database) == 2 && (
      toset([for s in aws_subnet.public : s.cidr_block]) == toset(["10.42.0.0/24", "10.42.1.0/24"]) &&
      toset([for s in aws_subnet.database : s.cidr_block]) == toset(["10.42.10.0/24", "10.42.11.0/24"]) &&
      toset([for s in aws_subnet.public : s.availability_zone]) == toset(["ap-northeast-1a", "ap-northeast-1c"]) &&
      toset([for s in aws_subnet.database : s.availability_zone]) == toset(["ap-northeast-1a", "ap-northeast-1c"])
    )
    error_message = "Two distinct Tokyo AZs need separate public and private /24 subnets."
  }
  assert {
    condition = alltrue(concat(
      [for s in aws_subnet.public : !s.map_public_ip_on_launch && s.vpc_id == "vpc-00000000000000001"],
      [for s in aws_subnet.database : !s.map_public_ip_on_launch && s.vpc_id == "vpc-00000000000000001"]
    ))
    error_message = "Subnets must belong to this VPC and never auto-assign public IPs."
  }
  assert {
    condition = length(aws_route_table.public.route) == 1 && alltrue([
      for r in aws_route_table.public.route : r.cidr_block == "0.0.0.0/0" && r.gateway_id == "igw-00000000000000001"
    ]) && length(aws_route_table.database.route) == 0 && length(aws_route_table_association.public) == 2 && length(aws_route_table_association.database) == 2
    error_message = "Only public subnets may have an internet default route."
  }
  assert {
    condition = toset(keys(aws_security_group.boundary)) == toset(["ingress", "app", "database"]) && (
      toset(keys(aws_vpc_security_group_ingress_rule.connection)) == toset(["app", "database"]) &&
      aws_vpc_security_group_ingress_rule.connection["app"].security_group_id == "sg-00000000000000002" &&
      aws_vpc_security_group_ingress_rule.connection["app"].referenced_security_group_id == "sg-00000000000000001" &&
      aws_vpc_security_group_ingress_rule.connection["app"].from_port == 8000 &&
      aws_vpc_security_group_ingress_rule.connection["app"].to_port == 8000 &&
      aws_vpc_security_group_ingress_rule.connection["database"].security_group_id == "sg-00000000000000003" &&
      aws_vpc_security_group_ingress_rule.connection["database"].referenced_security_group_id == "sg-00000000000000002" &&
      aws_vpc_security_group_ingress_rule.connection["database"].from_port == 5432 &&
      aws_vpc_security_group_ingress_rule.connection["database"].to_port == 5432 &&
      alltrue([for r in aws_vpc_security_group_ingress_rule.connection : r.ip_protocol == "tcp" && r.cidr_ipv4 == null && r.cidr_ipv6 == null && r.prefix_list_id == null])
    )
    error_message = "App and DB ingress must reference only the upstream SG on their exact TCP port."
  }
  assert {
    condition = toset(keys(aws_vpc_security_group_egress_rule.connection)) == toset(["ingress", "app"]) && (
      aws_vpc_security_group_egress_rule.connection["ingress"].security_group_id == "sg-00000000000000001" &&
      aws_vpc_security_group_egress_rule.connection["ingress"].referenced_security_group_id == "sg-00000000000000002" &&
      aws_vpc_security_group_egress_rule.connection["ingress"].from_port == 8000 &&
      aws_vpc_security_group_egress_rule.connection["ingress"].to_port == 8000 &&
      aws_vpc_security_group_egress_rule.connection["app"].security_group_id == "sg-00000000000000002" &&
      aws_vpc_security_group_egress_rule.connection["app"].referenced_security_group_id == "sg-00000000000000003" &&
      aws_vpc_security_group_egress_rule.connection["app"].from_port == 5432 &&
      aws_vpc_security_group_egress_rule.connection["app"].to_port == 5432 &&
      alltrue([for r in aws_vpc_security_group_egress_rule.connection : r.ip_protocol == "tcp" && r.cidr_ipv4 == null && r.cidr_ipv6 == null && r.prefix_list_id == null]) &&
      aws_vpc_security_group_egress_rule.https.security_group_id == "sg-00000000000000002" &&
      aws_vpc_security_group_egress_rule.https.ip_protocol == "tcp" &&
      aws_vpc_security_group_egress_rule.https.from_port == 443 && aws_vpc_security_group_egress_rule.https.to_port == 443 &&
      aws_vpc_security_group_egress_rule.https.cidr_ipv4 == "0.0.0.0/0" &&
      aws_vpc_security_group_egress_rule.https.cidr_ipv6 == null && aws_vpc_security_group_egress_rule.https.referenced_security_group_id == null
    )
    error_message = "Egress must be ingress->app:8000, app->DB:5432 and app->IPv4:443 only."
  }
  assert {
    condition = toset(keys(aws_vpc_security_group_rules_exclusive.boundary)) == toset(["ingress", "app", "database"]) && (
      aws_vpc_security_group_rules_exclusive.boundary["ingress"].ingress_rule_ids == toset(["sgr-00000000000000006"]) &&
      aws_vpc_security_group_rules_exclusive.boundary["ingress"].security_group_id == "sg-00000000000000001" &&
      aws_vpc_security_group_rules_exclusive.boundary["ingress"].egress_rule_ids == toset(["sgr-00000000000000003"]) &&
      aws_vpc_security_group_rules_exclusive.boundary["app"].security_group_id == "sg-00000000000000002" &&
      aws_vpc_security_group_rules_exclusive.boundary["app"].ingress_rule_ids == toset(["sgr-00000000000000001"]) &&
      aws_vpc_security_group_rules_exclusive.boundary["app"].egress_rule_ids == toset(["sgr-00000000000000004", "sgr-00000000000000005"]) &&
      aws_vpc_security_group_rules_exclusive.boundary["database"].security_group_id == "sg-00000000000000003" &&
      aws_vpc_security_group_rules_exclusive.boundary["database"].ingress_rule_ids == toset(["sgr-00000000000000002"]) &&
      length(aws_vpc_security_group_rules_exclusive.boundary["database"].egress_rule_ids) == 0
    )
    error_message = "Exclusive rule sets allow only the CloudFront ingress rule and keep DB egress empty."
  }
  assert {
    condition = toset(keys(aws_s3_bucket.private)) == toset(["static", "media"]) && (
      aws_s3_bucket.private["static"].bucket == "fitlog-demo-test-static-123456789012-ap-northeast-1" &&
      aws_s3_bucket.private["media"].bucket == "fitlog-demo-test-media-123456789012-ap-northeast-1" &&
      alltrue([for b in aws_s3_bucket.private : b.force_destroy == false]) &&
      toset(keys(aws_s3_bucket_public_access_block.private)) == toset(["static", "media"]) &&
      toset(keys(aws_s3_bucket_ownership_controls.private)) == toset(["static", "media"]) &&
      toset(keys(aws_s3_bucket_server_side_encryption_configuration.private)) == toset(["static", "media"]) &&
      alltrue([for k, b in aws_s3_bucket_public_access_block.private : b.bucket == "fitlog-demo-test-${k}-123456789012-ap-northeast-1"]) &&
      alltrue([for k, b in aws_s3_bucket_ownership_controls.private : b.bucket == "fitlog-demo-test-${k}-123456789012-ap-northeast-1"]) &&
      alltrue([for k, b in aws_s3_bucket_server_side_encryption_configuration.private : b.bucket == "fitlog-demo-test-${k}-123456789012-ap-northeast-1"]) &&
      alltrue([for b in aws_s3_bucket_public_access_block.private : b.block_public_acls && b.block_public_policy && b.ignore_public_acls && b.restrict_public_buckets]) &&
      alltrue([for b in aws_s3_bucket_ownership_controls.private : one(b.rule).object_ownership == "BucketOwnerEnforced"]) &&
      alltrue([for b in aws_s3_bucket_server_side_encryption_configuration.private : one(one(b.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"])
    )
    error_message = "Both dedicated buckets require all privacy/ownership/encryption protections and no forced deletion."
  }
  assert {
    condition = alltrue([for purpose, p in aws_s3_bucket_policy.tls : jsondecode(p.policy) == {
      Version = "2012-10-17"
      Statement = concat([{
        Sid       = "DenyInsecureTransport", Effect = "Deny", Principal = "*", Action = ["s3:*"],
        Resource  = ["arn:aws:s3:::fitlog-demo-test-${purpose}-123456789012-ap-northeast-1", "arn:aws:s3:::fitlog-demo-test-${purpose}-123456789012-ap-northeast-1/*"],
        Condition = { Bool = { "aws:SecureTransport" = "false", "aws:PrincipalIsAWSService" = "false" } }
        }], purpose == "static" ? [{
        Sid       = "CloudFrontStaticRead", Effect = "Allow", Principal = { Service = "cloudfront.amazonaws.com" },
        Action    = ["s3:GetObject"], Resource = ["arn:aws:s3:::fitlog-demo-test-static-123456789012-ap-northeast-1/*"],
        Condition = { StringEquals = { "AWS:SourceArn" = "arn:aws:cloudfront::123456789012:distribution/EFITLOGTEST" } }
      }] : [])
      }]) && toset(keys(aws_s3_bucket_policy.tls)) == toset(["static", "media"]) && alltrue([
      for k, p in aws_s3_bucket_policy.tls : p.bucket == "fitlog-demo-test-${k}-123456789012-ap-northeast-1"
    ])
    error_message = "Only static GetObject may be granted to this distribution; both buckets still deny insecure transport."
  }
  assert {
    condition = aws_ecr_repository.backend.name == "fitlog-demo-test/backend" && aws_ecr_repository.backend.image_tag_mutability == "IMMUTABLE" && (
      aws_ecr_repository.backend.force_delete == false && one(aws_ecr_repository.backend.image_scanning_configuration).scan_on_push &&
      one(aws_ecr_repository.backend.encryption_configuration).encryption_type == "AES256" &&
      aws_cloudwatch_log_group.backend.name == "/fitlog/fitlog-demo-test/backend" && aws_cloudwatch_log_group.backend.retention_in_days == 7
    )
    error_message = "Images must be immutable/scanned/encrypted and retained until explicitly emptied; logs expire after seven days."
  }
  assert {
    condition = toset(keys(aws_iam_role.ecs)) == toset(["task", "execution"]) && alltrue([
      for r in aws_iam_role.ecs : jsondecode(r.assume_role_policy) == {
        Version = "2012-10-17"
        Statement = [{
          Effect    = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = ["sts:AssumeRole"],
          Condition = { StringEquals = { "aws:SourceAccount" = "123456789012" }, ArnLike = { "aws:SourceArn" = "arn:aws:ecs:ap-northeast-1:123456789012:*" } }
        }]
      }
    ])
    error_message = "Only ECS tasks in the expected Tokyo account can assume the two roles."
  }
  assert {
    condition = jsondecode(aws_iam_role_policy.media.policy) == {
      Version = "2012-10-17"
      Statement = [
        { Sid = "ImageObjects", Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = ["arn:aws:s3:::fitlog-demo-test-media-123456789012-ap-northeast-1/images/*"] },
        { Sid = "ListImages", Effect = "Allow", Action = ["s3:ListBucket"], Resource = ["arn:aws:s3:::fitlog-demo-test-media-123456789012-ap-northeast-1"], Condition = { StringEquals = { "s3:prefix" = "images/" } } }
      ]
    } && aws_iam_role_policy.media.role == aws_iam_role.ecs["task"].id
    error_message = "Task policy may only access image objects and list images/; no other actions, prefixes or buckets."
  }
  assert {
    condition = jsondecode(aws_iam_role_policy.execution.policy) == {
      Version = "2012-10-17"
      Statement = [
        { Sid = "RegistryToken", Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = ["*"] },
        { Sid = "BackendImage", Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = ["arn:aws:ecr:ap-northeast-1:123456789012:repository/fitlog-demo-test/backend"] },
        { Sid = "BackendLogs", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["arn:aws:logs:ap-northeast-1:123456789012:log-group:/fitlog/fitlog-demo-test/backend:*"] }
      ]
    } && aws_iam_role_policy.execution.role == aws_iam_role.ecs["execution"].id
    error_message = "Execution policy may only retrieve backend images/token and write backend log streams."
  }
}
