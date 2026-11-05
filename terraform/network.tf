locals {
  subnets = { for index, az in var.availability_zones : tostring(index) => {
    az            = az
    public_cidr   = cidrsubnet("10.42.0.0/16", 8, index)
    database_cidr = cidrsubnet("10.42.0.0/16", 8, index + 10)
  } }
  connections = {
    app      = { source = "ingress", destination = "app", port = 8000 }
    database = { source = "app", destination = "database", port = 5432 }
  }
}

resource "aws_vpc" "foundation" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = var.environment_name }
}

resource "aws_internet_gateway" "public" {
  vpc_id = aws_vpc.foundation.id
  tags   = { Name = "${var.environment_name}-public" }
}

resource "aws_subnet" "public" {
  for_each                = local.subnets
  vpc_id                  = aws_vpc.foundation.id
  availability_zone       = each.value.az
  cidr_block              = each.value.public_cidr
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.environment_name}-public-${each.key}" }
}

resource "aws_subnet" "database" {
  for_each                = local.subnets
  vpc_id                  = aws_vpc.foundation.id
  availability_zone       = each.value.az
  cidr_block              = each.value.database_cidr
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.environment_name}-database-${each.key}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.foundation.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.public.id
  }
  tags = { Name = "${var.environment_name}-public" }
}

resource "aws_route_table" "database" {
  vpc_id = aws_vpc.foundation.id
  route  = []
  tags   = { Name = "${var.environment_name}-database" }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "database" {
  for_each       = aws_subnet.database
  subnet_id      = each.value.id
  route_table_id = aws_route_table.database.id
}

resource "aws_security_group" "boundary" {
  for_each    = toset(["ingress", "app", "database"])
  name        = "${var.environment_name}-${each.key}"
  description = "FitLog ${each.key}; explicit exclusive rules only"
  vpc_id      = aws_vpc.foundation.id
  tags        = { Name = "${var.environment_name}-${each.key}" }
}

resource "aws_vpc_security_group_ingress_rule" "connection" {
  for_each                     = local.connections
  security_group_id            = aws_security_group.boundary[each.value.destination].id
  referenced_security_group_id = aws_security_group.boundary[each.value.source].id
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
}

resource "aws_vpc_security_group_egress_rule" "connection" {
  for_each                     = { for c in values(local.connections) : c.source => c }
  security_group_id            = aws_security_group.boundary[each.value.source].id
  referenced_security_group_id = aws_security_group.boundary[each.value.destination].id
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.boundary["app"].id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# No inline SG rules: mixing them with standalone rules causes competing owners.
# CloudFront is the only public ingress; app/DB still accept only their upstream SG.
resource "aws_vpc_security_group_rules_exclusive" "boundary" {
  for_each          = aws_security_group.boundary
  security_group_id = each.value.id
  ingress_rule_ids = each.key == "ingress" ? [
    aws_vpc_security_group_ingress_rule.cloudfront.security_group_rule_id
    ] : [
    aws_vpc_security_group_ingress_rule.connection[each.key].security_group_rule_id
  ]
  egress_rule_ids = each.key == "ingress" ? [
    aws_vpc_security_group_egress_rule.connection["ingress"].security_group_rule_id
    ] : each.key == "app" ? [
    aws_vpc_security_group_egress_rule.connection["app"].security_group_rule_id,
    aws_vpc_security_group_egress_rule.https.security_group_rule_id
  ] : []
}
