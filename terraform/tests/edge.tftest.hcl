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
  values          = { id = "fitlog-demo-test-static-123456789012-ap-northeast-1", arn = "arn:aws:s3:::fitlog-demo-test-static-123456789012-ap-northeast-1", bucket_regional_domain_name = "fitlog-demo-test-static-123456789012-ap-northeast-1.s3.ap-northeast-1.amazonaws.com" }
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

# Contract oracle: docs/fl-09b3-edge-design.md; no AWS calls or policy overrides.
run "edge_boundary_and_routing" {
  command = plan

  assert {
    condition = (
      data.aws_ec2_managed_prefix_list.cloudfront.name == "com.amazonaws.global.cloudfront.origin-facing" &&
      aws_vpc_security_group_ingress_rule.cloudfront.security_group_id == "sg-00000000000000001" &&
      aws_vpc_security_group_ingress_rule.cloudfront.prefix_list_id == "pl-00000000000000001" &&
      aws_vpc_security_group_ingress_rule.cloudfront.ip_protocol == "tcp" &&
      aws_vpc_security_group_ingress_rule.cloudfront.from_port == 80 &&
      aws_vpc_security_group_ingress_rule.cloudfront.to_port == 80 &&
      aws_vpc_security_group_ingress_rule.cloudfront.cidr_ipv4 == null &&
      aws_vpc_security_group_ingress_rule.cloudfront.cidr_ipv6 == null &&
      aws_vpc_security_group_ingress_rule.cloudfront.referenced_security_group_id == null &&
      aws_vpc_security_group_rules_exclusive.boundary["ingress"].ingress_rule_ids == toset(["sgr-00000000000000006"])
    )
    error_message = "Only CloudFront origin-facing IPv4 TCP80 may enter the ALB SG."
  }
  assert {
    condition = (
      aws_lb.api.name == "fitlog-demo-test-api" &&
      aws_lb.api.load_balancer_type == "application" && !aws_lb.api.internal &&
      aws_lb.api.ip_address_type == "ipv4" && aws_lb.api.preserve_host_header &&
      aws_lb.api.drop_invalid_header_fields && aws_lb.api.idle_timeout == 65 &&
      aws_lb.api.security_groups == toset(["sg-00000000000000001"]) &&
      aws_lb.api.subnets == toset(["subnet-00000000000000001", "subnet-00000000000000002"]) &&
      alltrue([for log in aws_lb.api.access_logs : !log.enabled])
    )
    error_message = "The dedicated two-AZ ALB must preserve the viewer Host and its SG boundary."
  }
  assert {
    condition = (
      aws_lb_listener.api.load_balancer_arn == "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:loadbalancer/app/fitlog-demo-test/0000000000000000" &&
      aws_lb_listener.api.port == 80 && aws_lb_listener.api.protocol == "HTTP" &&
      length(aws_lb_listener.api.default_action) == 1 &&
      one(aws_lb_listener.api.default_action).type == "fixed-response" &&
      one(one(aws_lb_listener.api.default_action).fixed_response).status_code == "403" &&
      one(one(aws_lb_listener.api.default_action).fixed_response).content_type == "text/plain" &&
      aws_lb_listener_rule.cloudfront.listener_arn == "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:listener/app/fitlog-demo-test/0000000000000000/1111111111111111" &&
      length(aws_lb_listener_rule.cloudfront.condition) == 1 &&
      one(one(aws_lb_listener_rule.cloudfront.condition).http_header).http_header_name == "X-Fitlog-Origin-Verify" &&
      toset(one(one(aws_lb_listener_rule.cloudfront.condition).http_header).values) == toset(["0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"]) &&
      length(aws_lb_listener_rule.cloudfront.action) == 1 &&
      one(aws_lb_listener_rule.cloudfront.action).type == "forward" &&
      one(aws_lb_listener_rule.cloudfront.action).target_group_arn == "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:targetgroup/fitlog-demo-test/0000000000000000"
    )
    error_message = "A nonmatching secret must stay denied; the single matching rule forwards to this target group only."
  }
  assert {
    condition = (
      aws_lb_target_group.api.vpc_id == "vpc-00000000000000001" &&
      aws_lb_target_group.api.target_type == "ip" && aws_lb_target_group.api.protocol == "HTTP" && aws_lb_target_group.api.port == 8000 &&
      one(aws_lb_target_group.api.health_check).enabled &&
      one(aws_lb_target_group.api.health_check).path == "/api/health/live" &&
      one(aws_lb_target_group.api.health_check).protocol == "HTTP" &&
      one(aws_lb_target_group.api.health_check).matcher == "200" &&
      one(aws_lb_target_group.api.health_check).interval == 30 &&
      one(aws_lb_target_group.api.health_check).timeout == 5 &&
      one(aws_lb_target_group.api.health_check).healthy_threshold == 2 &&
      one(aws_lb_target_group.api.health_check).unhealthy_threshold == 2
    )
    error_message = "Future ECS IP targets use TCP8000 and DB-independent liveness, never readiness."
  }
  assert {
    condition = (
      !aws_cloudfront_distribution.edge.enabled && aws_cloudfront_distribution.edge.is_ipv6_enabled &&
      aws_cloudfront_distribution.edge.http_version == "http2" &&
      aws_cloudfront_distribution.edge.aliases == null &&
      one(aws_cloudfront_distribution.edge.viewer_certificate).cloudfront_default_certificate &&
      aws_cloudfront_distribution.edge.default_root_object == "index.html" &&
      !aws_cloudfront_distribution.edge.retain_on_delete && aws_cloudfront_distribution.edge.wait_for_deployment &&
      length(aws_cloudfront_distribution.edge.origin) == 2
    )
    error_message = "The default distribution stays disabled and uses only its AWS HTTPS domain and two dedicated origins."
  }
  assert {
    condition = (
      length(aws_cloudfront_distribution.edge.ordered_cache_behavior) == 2 &&
      toset([for b in aws_cloudfront_distribution.edge.ordered_cache_behavior : b.path_pattern]) == toset(["/api", "/api/*"]) &&
      alltrue([for b in aws_cloudfront_distribution.edge.ordered_cache_behavior : (
        b.target_origin_id == "api" && b.viewer_protocol_policy == "https-only" && !b.compress &&
        toset(b.allowed_methods) == toset(["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]) &&
        toset(b.cached_methods) == toset(["GET", "HEAD"]) &&
        b.cache_policy_id == "00000000-0000-0000-0000-000000000001" &&
        b.origin_request_policy_id == "00000000-0000-0000-0000-000000000002" &&
        length(b.function_association) == 1 &&
        one(b.function_association).event_type == "viewer-request" &&
        one(b.function_association).function_arn == "arn:aws:cloudfront::123456789012:function/fitlog-demo-test-client-ip"
      )]) &&
      aws_cloudfront_function.client_ip.runtime == "cloudfront-js-2.0" && aws_cloudfront_function.client_ip.publish &&
      aws_cloudfront_function.client_ip.code == file("functions/client-ip.js")
    )
    error_message = "Both bare and nested API routes must bypass cache, forward all methods and replace the viewer IP."
  }
  assert {
    condition = (
      aws_cloudfront_cache_policy.disabled.min_ttl == 0 && aws_cloudfront_cache_policy.disabled.default_ttl == 0 && aws_cloudfront_cache_policy.disabled.max_ttl == 0 &&
      !one(aws_cloudfront_cache_policy.disabled.parameters_in_cache_key_and_forwarded_to_origin).enable_accept_encoding_gzip &&
      !one(aws_cloudfront_cache_policy.disabled.parameters_in_cache_key_and_forwarded_to_origin).enable_accept_encoding_brotli &&
      one(one(aws_cloudfront_cache_policy.disabled.parameters_in_cache_key_and_forwarded_to_origin).headers_config).header_behavior == "none" &&
      one(one(aws_cloudfront_cache_policy.disabled.parameters_in_cache_key_and_forwarded_to_origin).cookies_config).cookie_behavior == "none" &&
      one(one(aws_cloudfront_cache_policy.disabled.parameters_in_cache_key_and_forwarded_to_origin).query_strings_config).query_string_behavior == "none" &&
      one(aws_cloudfront_origin_request_policy.api.headers_config).header_behavior == "allViewer" &&
      one(aws_cloudfront_origin_request_policy.api.cookies_config).cookie_behavior == "all" &&
      one(aws_cloudfront_origin_request_policy.api.query_strings_config).query_string_behavior == "all"
    )
    error_message = "TTL0 prevents shared caching while all viewer headers (including Host/CSRF/IP), cookies and queries reach the API."
  }
  assert {
    condition = (
      one(aws_cloudfront_distribution.edge.default_cache_behavior).target_origin_id == "static" &&
      one(aws_cloudfront_distribution.edge.default_cache_behavior).viewer_protocol_policy == "https-only" &&
      !one(aws_cloudfront_distribution.edge.default_cache_behavior).compress &&
      toset(one(aws_cloudfront_distribution.edge.default_cache_behavior).allowed_methods) == toset(["GET", "HEAD"]) &&
      toset(one(aws_cloudfront_distribution.edge.default_cache_behavior).cached_methods) == toset(["GET", "HEAD"]) &&
      one(aws_cloudfront_distribution.edge.default_cache_behavior).cache_policy_id == "00000000-0000-0000-0000-000000000001" &&
      one(aws_cloudfront_distribution.edge.default_cache_behavior).origin_request_policy_id == null &&
      length(one(aws_cloudfront_distribution.edge.default_cache_behavior).function_association) == 0
    )
    error_message = "Static origin accepts only reads with no viewer values or API Function."
  }
  assert {
    condition = alltrue([for o in aws_cloudfront_distribution.edge.origin : o.origin_id == "api" ? (
      o.domain_name == "fitlog-demo-test.ap-northeast-1.elb.amazonaws.com" &&
      one(o.custom_origin_config).origin_protocol_policy == "http-only" &&
      one(o.custom_origin_config).http_port == 80 && one(o.custom_origin_config).origin_read_timeout == 60 &&
      { for h in o.custom_header : h.name => h.value } == {
        "X-Fitlog-Origin-Verify"   = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        "X-Fitlog-Forwarded-Proto" = "https"
      }
      ) : (
      o.origin_id == "static" &&
      o.domain_name == "fitlog-demo-test-static-123456789012-ap-northeast-1.s3.ap-northeast-1.amazonaws.com" &&
      o.origin_access_control_id == "EFITLOGOAC" && length(o.custom_header) == 0 && length(o.custom_origin_config) == 0
      )]) && (
      aws_cloudfront_origin_access_control.static.origin_access_control_origin_type == "s3" &&
      aws_cloudfront_origin_access_control.static.signing_behavior == "always" &&
      aws_cloudfront_origin_access_control.static.signing_protocol == "sigv4"
    )
    error_message = "Only API origin carries overwrite headers; static must use its regional REST endpoint and always-signed OAC."
  }
  assert {
    condition = (
      toset([for e in aws_cloudfront_distribution.edge.custom_error_response : e.error_code]) == toset([400, 403, 404, 405, 414, 416, 500, 501, 502, 503, 504]) &&
      alltrue([for e in aws_cloudfront_distribution.edge.custom_error_response : e.error_caching_min_ttl == 0 && e.response_code == null && e.response_page_path == null])
    )
    error_message = "Error responses must not be cached or rewritten to SPA HTML/status200."
  }
  assert {
    condition = output.distribution == {
      id          = "EFITLOGTEST", arn = "arn:aws:cloudfront::123456789012:distribution/EFITLOGTEST",
      domain_name = "dfitlogtest.cloudfront.net", url = "https://dfitlogtest.cloudfront.net"
    } && output.api_target_group_arn == "arn:aws:elasticloadbalancing:ap-northeast-1:123456789012:targetgroup/fitlog-demo-test/0000000000000000"
    error_message = "Follow-up runtime receives identifiers and a future URL, never the origin secret or a readiness assertion."
  }
}

run "explicit_public_opt_in" {
  command = plan
  variables { enable_public_distribution = true }
  assert {
    condition     = aws_cloudfront_distribution.edge.enabled
    error_message = "Only an explicit public opt-in enables the distribution."
  }
}
