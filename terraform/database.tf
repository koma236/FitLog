resource "aws_db_subnet_group" "runtime" {
  name       = "${var.environment_name}-database"
  subnet_ids = [for subnet in aws_subnet.database : subnet.id]
}

resource "aws_db_parameter_group" "runtime" {
  name   = "${var.environment_name}-postgres17"
  family = "postgres17"
  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
}

resource "aws_db_instance" "runtime" {
  identifier                  = var.environment_name
  engine                      = "postgres"
  engine_version              = var.postgres_engine_version
  instance_class              = "db.t4g.micro"
  db_name                     = "fitlog"
  username                    = "fitlog_admin"
  port                        = 5432
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.runtime.name
  parameter_group_name        = aws_db_parameter_group.runtime.name
  vpc_security_group_ids      = [aws_security_group.boundary["database"].id]
  publicly_accessible         = false
  multi_az                    = false
  storage_type                = "gp3"
  allocated_storage           = 20
  storage_encrypted           = true
  ca_cert_identifier          = "rds-ca-rsa2048-g1"
  auto_minor_version_upgrade  = false
  allow_major_version_upgrade = false
  backup_retention_period     = 1
  delete_automated_backups    = false
  deletion_protection         = true
  skip_final_snapshot         = false
  final_snapshot_identifier   = var.db_final_snapshot_identifier
  apply_immediately           = false
}
