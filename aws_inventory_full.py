import boto3
import pandas as pd

rows = []

def add(
    service,
    rtype,
    rid,
    name,
    status,
    region,
    arn="",
    instance_type="",
    created_date="",
    tags="",
    owner="",
    engine="",
    version="",
    size="",
    public_ip="",
    private_ip="",
    vpc_id="",
    subnet_id=""
):
    rows.append([
        service,
        rtype,
        rid,
        name,
        status,
        region,
        arn,
        instance_type,
        created_date,
        tags,
        owner,
        engine,
        version,
        size,
        public_ip,
        private_ip,
        vpc_id,
        subnet_id
    ])


# =========================
# GET ALL REGIONS
# =========================
ec2_global = boto3.client("ec2")
regions = [r["RegionName"] for r in ec2_global.describe_regions()["Regions"]]


# =========================
# GLOBAL CLIENTS
# =========================
s3 = boto3.client("s3")
iam = boto3.client("iam")
cloudtrail = boto3.client("cloudtrail")
ce = boto3.client("ce")


# =========================
# GLOBAL RESOURCES
# =========================

for b in s3.list_buckets()["Buckets"]:
    add("STORAGE", "S3 Bucket", b["Name"], b["Name"], "active", "global")

for r in iam.list_roles()["Roles"]:
    add("SECURITY", "IAM Role", r["RoleId"], r["RoleName"], "active", "global")

for t in cloudtrail.describe_trails()["trailList"]:
    add("MONITORING", "CloudTrail", t["TrailARN"], t["Name"], "active", "global")

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
    for r in ec2.describe_instances()["Reservations"]:
        for i in r["Instances"]:

            name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "")
            tags = "; ".join([f"{t['Key']}={t['Value']}" for t in i.get("Tags", [])])

            add(
                "EC2",
                "Instance",
                i["InstanceId"],
                name,
                i["State"]["Name"],
                REGION,
                arn=f"arn:aws:ec2:{REGION}::instance/{i['InstanceId']}",
                instance_type=i.get("InstanceType", ""),
                created_date=str(i.get("LaunchTime", "")),
                tags=tags,
                public_ip=i.get("PublicIpAddress", ""),
                private_ip=i.get("PrivateIpAddress", ""),
                vpc_id=i.get("VpcId", ""),
                subnet_id=i.get("SubnetId", "")
            )

    # ---------------- VPC ----------------
    for v in ec2.describe_vpcs()["Vpcs"]:
        name = ""
        for tag in v.get("Tags", []):
            if tag["Key"] == "Name":
                name = tag["Value"]

        add(
            "NETWORK",
            "VPC",
            v["VpcId"],
            name,
            "active",
            REGION,
            tags=str(v.get("Tags", ""))
        )

    # ---------------- Subnets ----------------
    for s in ec2.describe_subnets()["Subnets"]:
        name = ""
        for tag in s.get("Tags", []):
            if tag["Key"] == "Name":
                name = tag["Value"]

        add(
            "NETWORK",
            "Subnet",
            s["SubnetId"],
            name,
            "active",
            REGION,
            tags=str(s.get("Tags", "")),
            vpc_id=s.get("VpcId", "")
        )

    # ---------------- Security Groups ----------------
    for sg in ec2.describe_security_groups()["SecurityGroups"]:
        add("NETWORK", "SecurityGroup", sg["GroupId"], sg["GroupName"], "active", REGION)

    # ---------------- Volumes ----------------
    for v in ec2.describe_volumes()["Volumes"]:
        name = ""
        for tag in v.get("Tags", []):
            if tag["Key"] == "Name":
                name = tag["Value"]

        add(
            "EC2",
            "EBS Volume",
            v["VolumeId"],
            name,
            v["State"],
            REGION,
            size=str(v["Size"]),
            created_date=str(v["CreateTime"]),
            tags=str(v.get("Tags", ""))
        )

    # ---------------- Elastic IP ----------------
    for e in ec2.describe_addresses()["Addresses"]:
        add("NETWORK", "ElasticIP", e.get("AllocationId",""), e.get("PublicIp",""), "active", REGION)

    # ---------------- Snapshots ----------------
    try:
        snapshots = ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]
        for s in snapshots:
            add(
                "EC2",
                "EBS Snapshot",
                s["SnapshotId"],
                s.get("Description", ""),
                s["State"],
                REGION,
                size=str(s.get("VolumeSize", "")),
                created_date=str(s["StartTime"])
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

    # ---------------- ECS ----------------
    ecs = boto3.client("ecs", region_name=REGION)
    for c in ecs.list_clusters()["clusterArns"]:
        add("CONTAINERS", "ECS", c, c.split("/")[-1], "active", REGION)

    # ---------------- EKS ----------------
    eks = boto3.client("eks", region_name=REGION)
    for cluster_name in eks.list_clusters()["clusters"]:
        cluster = eks.describe_cluster(name=cluster_name)["cluster"]

        add(
            "CONTAINERS",
            "EKS",
            cluster["arn"],
            cluster["name"],
            cluster["status"],
            REGION,
            arn=cluster["arn"],
            version=cluster["version"],
            created_date=str(cluster["createdAt"])
        )

    # ---------------- ECR ----------------
    ecr = boto3.client("ecr", region_name=REGION)
    try:
        repos = ecr.describe_repositories()["repositories"]
        for r in repos:
            images = ecr.list_images(repositoryName=r["repositoryName"])["imageIds"]
            for img in images:
                add("CONTAINERS", "ECR Image", r["repositoryName"], str(img), "active", REGION)
    except:
        pass

    # ---------------- Lambda ----------------
    lam = boto3.client("lambda", region_name=REGION)
    for f in lam.list_functions()["Functions"]:
        add(
            "SERVERLESS",
            "Lambda",
            f["FunctionArn"],
            f["FunctionName"],
            "active",
            REGION,
            arn=f["FunctionArn"],
            version=f["Runtime"],
            created_date=str(f["LastModified"])
        )

    # ---------------- Step Functions ----------------
    sf = boto3.client("stepfunctions", region_name=REGION)
    try:
        for s in sf.list_state_machines()["stateMachines"]:
            add("SERVERLESS", "StepFunctions", s["stateMachineArn"], s["name"], "active", REGION)
    except:
        pass

    # ---------------- RDS ----------------
    rds = boto3.client("rds", region_name=REGION)
    for db in rds.describe_db_instances()["DBInstances"]:
        add(
            "DATABASES",
            "RDS",
            db["DBInstanceIdentifier"],
            db["DBInstanceIdentifier"],
            db["DBInstanceStatus"],
            REGION,
            arn=db["DBInstanceArn"],
            instance_type=db["DBInstanceClass"],
            engine=db["Engine"],
            version=db["EngineVersion"],
            created_date=str(db["InstanceCreateTime"])
        )

    # ---------------- DynamoDB ----------------
    ddb = boto3.client("dynamodb", region_name=REGION)
    for t in ddb.list_tables()["TableNames"]:
        add("DATABASES", "DynamoDB", t, t, "active", REGION)

    # ---------------- Redshift ----------------
    redshift = boto3.client("redshift", region_name=REGION)
    try:
        for c in redshift.describe_clusters()["Clusters"]:
            add("DATABASES", "Redshift", c["ClusterIdentifier"], "", c["ClusterStatus"], REGION)
    except:
        pass

    # ---------------- KMS ----------------
    kms = boto3.client("kms", region_name=REGION)
    try:
        for k in kms.list_keys()["Keys"]:
            add("SECURITY", "KMS", k["KeyId"], "", "active", REGION)
    except:
        pass

    # ---------------- Secrets Manager ----------------
    secrets = boto3.client("secretsmanager", region_name=REGION)
    try:
        for s in secrets.list_secrets()["SecretList"]:
            add("SECURITY", "SecretsManager", s["ARN"], s.get("Name",""), "active", REGION)
    except:
        pass

    # ---------------- SNS ----------------
    sns = boto3.client("sns", region_name=REGION)
    for t in sns.list_topics()["Topics"]:
        add("MESSAGING", "SNS Topic", t["TopicArn"], t["TopicArn"].split(":")[-1], "active", REGION)

    # ---------------- SQS ----------------
    sqs = boto3.client("sqs", region_name=REGION)
    try:
        for q in sqs.list_queues().get("QueueUrls", []):
            add("MESSAGING", "SQS Queue", q, q.split("/")[-1], "active", REGION)
    except:
        pass

    # ---------------- CloudFront ----------------
    cloudfront = boto3.client("cloudfront")
    for dist in cloudfront.list_distributions().get("DistributionList", {}).get("Items", []):
        add("NETWORK", "CloudFront Distribution", dist["Id"], dist["DomainName"], dist["Status"], "global")

    # ---------------- CloudWatch ----------------
    cw = boto3.client("cloudwatch", region_name=REGION)
    for a in cw.describe_alarms()["MetricAlarms"]:
        add("MONITORING", "CloudWatch Alarm", a["AlarmName"], a["AlarmName"], a["StateValue"], REGION)

    # ---------------- Logs ----------------
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
    "Service",
    "ResourceType",
    "ResourceId",
    "Name",
    "Status",
    "Region",
    "ARN",
    "InstanceType",
    "CreatedDate",
    "Tags",
    "Owner",
    "Engine",
    "Version",
    "Size",
    "PublicIP",
    "PrivateIP",
    "VPCId",
    "SubnetId"
])

df.to_excel("aws_inventory_COMPLETE.xlsx", index=False)
df.to_csv("aws_inventory_COMPLETE.csv", index=False)

print("\n✅ COMPLETE AWS INVENTORY GENERATED (FIXED)")