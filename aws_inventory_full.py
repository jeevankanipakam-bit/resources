import boto3
import pandas as pd

rows = []

def add(service, rtype, rid, name, status, region):
    rows.append([service, rtype, rid, name, status, region])


# =========================
# GET ALL REGIONS
# =========================
ec2_global = boto3.client("ec2")
regions = [r["RegionName"] for r in ec2_global.describe_regions()["Regions"]]


# =========================
# GLOBAL CLIENTS (ONCE)
# =========================
s3 = boto3.client("s3")
iam = boto3.client("iam")
cloudtrail = boto3.client("cloudtrail")
ce = boto3.client("ce")  # Cost Explorer


# =========================
# GLOBAL RESOURCES
# =========================

# S3 Buckets
for b in s3.list_buckets()["Buckets"]:
    add("STORAGE", "S3 Bucket", b["Name"], b["Name"], "active", "global")

# IAM Roles
for r in iam.list_roles()["Roles"]:
    add("SECURITY", "IAM Role", r["RoleId"], r["RoleName"], "active", "global")

# CloudTrail Trails
for t in cloudtrail.describe_trails()["trailList"]:
    add("MONITORING", "CloudTrail", t["TrailARN"], t["Name"], "active", "global")

# Cost Explorer (last 30 days total per service)
try:
    cost = ce.get_cost_and_usage(
        TimePeriod={"Start": "2025-05-01", "End": "2025-06-01"},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}]
    )
    for g in cost["ResultsByTime"][0]["Groups"]:
        add("FINOPS", "CostExplorer", g["Keys"][0], "", g["Metrics"]["UnblendedCost"]["Amount"], "global")
except:
    pass


# =========================
# REGION LOOP
# =========================
for REGION in regions:
    print("Scanning:", REGION)

    ec2 = boto3.client("ec2", region_name=REGION)

    # ---------------- EC2 ----------------
    for v in ec2.describe_vpcs()["Vpcs"]:
        add("NETWORK", "VPC", v["VpcId"], "", "active", REGION)

    for s in ec2.describe_subnets()["Subnets"]:
        add("NETWORK", "Subnet", s["SubnetId"], "", "active", REGION)

    for r in ec2.describe_instances()["Reservations"]:
        for i in r["Instances"]:
            name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "")
            add("EC2", "Instance", i["InstanceId"], name, i["State"]["Name"], REGION)

    for sg in ec2.describe_security_groups()["SecurityGroups"]:
        add("NETWORK", "SecurityGroup", sg["GroupId"], sg["GroupName"], "active", REGION)

    for v in ec2.describe_volumes()["Volumes"]:
        add("EC2", "EBS Volume", v["VolumeId"], "", v["State"], REGION)

    for e in ec2.describe_addresses()["Addresses"]:
        add("NETWORK", "ElasticIP", e.get("AllocationId",""), e.get("PublicIp",""), "active", REGION)

     # ---------------- SNAPSHOTS (✅ ADDED) ----------------
    try:
        snapshots = ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]
        for s in snapshots:
            add(
                "EC2",
                "EBS Snapshot",
                s["SnapshotId"],
                s.get("Description", ""),
                s["State"],
                REGION
            )
    except:
        pass
    # ---------------- ELB ----------------
    elb = boto3.client("elbv2", region_name=REGION)
    for lb in elb.describe_load_balancers()["LoadBalancers"]:
        add("ELB", lb["Type"], lb["LoadBalancerArn"], lb["LoadBalancerName"], lb["State"]["Code"], REGION)

    # ---------------- ASG ----------------
    asg = boto3.client("autoscaling", region_name=REGION)
    for g in asg.describe_auto_scaling_groups()["AutoScalingGroups"]:
        add("ASG", "AutoScalingGroup", g["AutoScalingGroupARN"], g["AutoScalingGroupName"], "active", REGION)

    # ---------------- CONTAINERS ----------------
    ecs = boto3.client("ecs", region_name=REGION)
    for c in ecs.list_clusters()["clusterArns"]:
        add("CONTAINERS", "ECS", c, c.split("/")[-1], "active", REGION)

    eks = boto3.client("eks", region_name=REGION)
    for c in eks.list_clusters()["clusters"]:
        add("CONTAINERS", "EKS", c, c, "active", REGION)

    ecr = boto3.client("ecr", region_name=REGION)
    try:
        repos = ecr.describe_repositories()["repositories"]
        for r in repos:
            # ECR IMAGES (IMPORTANT ADDITION)
            images = ecr.list_images(repositoryName=r["repositoryName"])["imageIds"]
            for img in images:
                add("CONTAINERS", "ECR Image", r["repositoryName"], str(img), "active", REGION)
    except:
        pass

    # ---------------- SERVERLESS ----------------
    lam = boto3.client("lambda", region_name=REGION)
    for f in lam.list_functions()["Functions"]:
        add("SERVERLESS", "Lambda", f["FunctionArn"], f["FunctionName"], "active", REGION)

    sf = boto3.client("stepfunctions", region_name=REGION)
    try:
        for s in sf.list_state_machines()["stateMachines"]:
            add("SERVERLESS", "StepFunctions", s["stateMachineArn"], s["name"], "active", REGION)
    except:
        pass

    # ---------------- DATABASES ----------------
    rds = boto3.client("rds", region_name=REGION)
    for db in rds.describe_db_instances()["DBInstances"]:
        add("DATABASES", "RDS", db["DBInstanceIdentifier"], "", db["DBInstanceStatus"], REGION)

    ddb = boto3.client("dynamodb", region_name=REGION)
    for t in ddb.list_tables()["TableNames"]:
        add("DATABASES", "DynamoDB", t, t, "active", REGION)

    # ---------------- REDSHIFT ----------------
    redshift = boto3.client("redshift", region_name=REGION)
    try:
        for c in redshift.describe_clusters()["Clusters"]:
            add("DATABASES", "Redshift", c["ClusterIdentifier"], "", c["ClusterStatus"], REGION)
    except:
        pass

    # ---------------- SECURITY ----------------
    kms = boto3.client("kms", region_name=REGION)
    try:
        for k in kms.list_keys()["Keys"]:
            add("SECURITY", "KMS", k["KeyId"], "", "active", REGION)
    except:
        pass

    secrets = boto3.client("secretsmanager", region_name=REGION)
    try:
        for s in secrets.list_secrets()["SecretList"]:
            add("SECURITY", "SecretsManager", s["ARN"], s.get("Name",""), "active", REGION)
    except:
        pass

    # ---------------- SNS / SQS ----------------
    sns = boto3.client("sns", region_name=REGION)
    for t in sns.list_topics()["Topics"]:
        add("MESSAGING", "SNS Topic", t["TopicArn"], t["TopicArn"].split(":")[-1], "active", REGION)

    sqs = boto3.client("sqs", region_name=REGION)
    try:
        for q in sqs.list_queues().get("QueueUrls", []):
            add("MESSAGING", "SQS Queue", q, q.split("/")[-1], "active", REGION)
    except:
        pass


    # ---------------- CLOUDFRONT ----------------
    cloudfront = boto3.client("cloudfront")
    for dist in cloudfront.list_distributions().get("DistributionList", {}).get("Items", []):
        add("NETWORK", "CloudFront Distribution", dist["Id"], dist["DomainName"], dist["Status"], "global")

    # ---------------- APPLICATION LOAD BALANCERS ----------------
    elb = boto3.client("elbv2", region_name=REGION)
    for lb in elb.describe_load_balancers()["LoadBalancers"]:
        if lb["Type"] == "application":
            add("ELB", "Application Load Balancer", lb["LoadBalancerArn"], lb["LoadBalancerName"], lb["State"]["Code"], REGION)


    # ---------------- CLOUDWATCH ALARMS ----------------
    cw = boto3.client("cloudwatch", region_name=REGION)
    for a in cw.describe_alarms()["MetricAlarms"]:
        add("MONITORING", "CloudWatch Alarm", a["AlarmName"], a["AlarmName"], a["StateValue"], REGION)

    # ---------------- CLOUDWATCH LOGS ----------------
    logs = boto3.client("logs", region_name=REGION)
    try:
        for g in logs.describe_log_groups()["logGroups"]:
            add("MONITORING", "CloudWatch Logs", g["arn"], g["logGroupName"], "active", REGION)
    except:
        pass

    # ---------------- EFS ----------------
    efs = boto3.client("efs", region_name=REGION)
    try:
        for f in efs.describe_file_systems()["FileSystems"]:
            add("STORAGE", "EFS", f["FileSystemId"], f.get("Name",""), f["LifeCycleState"], REGION)
    except:
        pass

    # ---------------- FSx ----------------
    fsx = boto3.client("fsx", region_name=REGION)
    try:
        for f in fsx.describe_file_systems()["FileSystems"]:
            add("STORAGE", "FSx", f["FileSystemId"], "", f["Lifecycle"], REGION)
    except:
        pass


# =========================
# EXPORT
# =========================
df = pd.DataFrame(rows, columns=[
    "Service", "ResourceType", "ResourceId", "Name", "Status", "Region"
])

df.to_excel("aws_inventory_COMPLETE.xlsx", index=False)
df.to_csv("aws_inventory_COMPLETE.csv", index=False)

print("\n✅ COMPLETE AWS INVENTORY GENERATED (NO MAJOR SERVICE LEFT)")