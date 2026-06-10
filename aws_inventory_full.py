import boto3
import pandas as pd

REGION = "ap-south-1"
rows = []

def add(service, rtype, rid, name, status, region):
    rows.append([service, rtype, rid, name, status, region])


# =========================
# EC2 / NETWORKING
# =========================
ec2 = boto3.client("ec2", region_name=REGION)

for v in ec2.describe_vpcs()["Vpcs"]:
    add("EC2", "VPC", v["VpcId"], "", "active", REGION)

for s in ec2.describe_subnets()["Subnets"]:
    add("EC2", "Subnet", s["SubnetId"], "", "active", REGION)

for r in ec2.describe_instances()["Reservations"]:
    for i in r["Instances"]:
        name = ""
        for t in i.get("Tags", []):
            if t["Key"] == "Name":
                name = t["Value"]
        add("EC2", "Instance", i["InstanceId"], name, i["State"]["Name"], REGION)

for sg in ec2.describe_security_groups()["SecurityGroups"]:
    add("EC2", "SecurityGroup", sg["GroupId"], sg["GroupName"], "active", REGION)

for v in ec2.describe_volumes()["Volumes"]:
    add("EC2", "EBS Volume", v["VolumeId"], "", v["State"], REGION)

for s in ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]:
    add("EC2", "Snapshot", s["SnapshotId"], "", "active", REGION)

for e in ec2.describe_addresses()["Addresses"]:
    add("EC2", "ElasticIP", e.get("AllocationId",""), e.get("PublicIp",""), "active", REGION)

for a in ec2.describe_images(Owners=["self"])["Images"]:
    add("EC2", "AMI", a["ImageId"], a.get("Name",""), a["State"], REGION)


# =========================
# LOAD BALANCER
# =========================
elb = boto3.client("elbv2", region_name=REGION)

for lb in elb.describe_load_balancers()["LoadBalancers"]:
    add("ELB", lb["Type"], lb["LoadBalancerArn"], lb["LoadBalancerName"], lb["State"]["Code"], REGION)


# =========================
# AUTO SCALING
# =========================
asg = boto3.client("autoscaling", region_name=REGION)

for g in asg.describe_auto_scaling_groups()["AutoScalingGroups"]:
    add("ASG", "AutoScalingGroup", g["AutoScalingGroupARN"], g["AutoScalingGroupName"], "active", REGION)


# =========================
# CONTAINERS
# =========================
ecs = boto3.client("ecs", region_name=REGION)
for c in ecs.list_clusters()["clusterArns"]:
    add("ECS", "Cluster", c, c.split("/")[-1], "active", REGION)

eks = boto3.client("eks", region_name=REGION)
for c in eks.list_clusters()["clusters"]:
    add("EKS", "Cluster", c, c, "active", REGION)

ecr = boto3.client("ecr", region_name=REGION)
try:
    for r in ecr.describe_repositories()["repositories"]:
        add("ECR", "Repository", r["repositoryArn"], r["repositoryName"], "active", REGION)
except:
    pass


# =========================
# SERVERLESS
# =========================
lam = boto3.client("lambda", region_name=REGION)
for f in lam.list_functions()["Functions"]:
    add("Lambda", "Function", f["FunctionArn"], f["FunctionName"], "active", REGION)

sf = boto3.client("stepfunctions", region_name=REGION)
for s in sf.list_state_machines()["stateMachines"]:
    add("StepFunctions", "StateMachine", s["stateMachineArn"], s["name"], "active", REGION)

events = boto3.client("events", region_name=REGION)
for r in events.list_rules()["Rules"]:
    add("EventBridge", "Rule", r["Arn"], r["Name"], "active", REGION)


# =========================
# STORAGE / DATABASES
# =========================
s3 = boto3.client("s3")
for b in s3.list_buckets()["Buckets"]:
    add("S3", "Bucket", b["Name"], b["Name"], "active", "global")

rds = boto3.client("rds", region_name=REGION)
for db in rds.describe_db_instances()["DBInstances"]:
    add("RDS", "DBInstance", db["DBInstanceIdentifier"], "", db["DBInstanceStatus"], REGION)

ddb = boto3.client("dynamodb", region_name=REGION)
for t in ddb.list_tables()["TableNames"]:
    add("DynamoDB", "Table", t, t, "active", REGION)

elasticache = boto3.client("elasticache", region_name=REGION)
for c in elasticache.describe_cache_clusters()["CacheClusters"]:
    add("ElastiCache", "Cluster", c["CacheClusterId"], "", c["CacheClusterStatus"], REGION)


# =========================
# REDSHIFT (FIXED)
# =========================
try:
    redshift = boto3.client("redshift", region_name=REGION)
    clusters = redshift.describe_clusters()["Clusters"]
    for c in clusters:
        add("Redshift", "Cluster", c["ClusterIdentifier"], "", c["ClusterStatus"], REGION)
except Exception:
    add("Redshift", "Cluster", "NOT_ENABLED", "Redshift not enabled", "inactive", REGION)


# =========================
# SECURITY
# =========================
iam = boto3.client("iam")
for r in iam.list_roles()["Roles"]:
    add("IAM", "Role", r["RoleId"], r["RoleName"], "active", "global")


kms = boto3.client("kms", region_name=REGION)
try:
    for k in kms.list_keys()["Keys"]:
        add("KMS", "Key", k["KeyId"], "", "active", REGION)
except:
    pass

secrets = boto3.client("secretsmanager", region_name=REGION)
try:
    for s in secrets.list_secrets()["SecretList"]:
        add("SecretsManager", "Secret", s["ARN"], s.get("Name",""), "active", REGION)
except:
    pass


# =========================
# MONITORING
# =========================
cw = boto3.client("cloudwatch", region_name=REGION)
for a in cw.describe_alarms()["MetricAlarms"]:
    add("CloudWatch", "Alarm", a["AlarmName"], a["AlarmName"], a["StateValue"], REGION)


# =========================
# MESSAGING
# =========================
sns = boto3.client("sns", region_name=REGION)
for t in sns.list_topics()["Topics"]:
    add("SNS", "Topic", t["TopicArn"], t["TopicArn"].split(":")[-1], "active", REGION)

sqs = boto3.client("sqs", region_name=REGION)
try:
    for q in sqs.list_queues()["QueueUrls"]:
        add("SQS", "Queue", q, q.split("/")[-1], "active", REGION)
except:
    pass


# =========================
# OUTPUT
# =========================
df = pd.DataFrame(rows, columns=[
    "Service",
    "ResourceType",
    "ResourceId",
    "Name",
    "Status",
    "Region"
])

print("\n================ AWS FULL INVENTORY ================\n")
print(df.to_string(index=False))

df.to_excel("aws_inventory.xlsx", index=False)
df.to_csv("aws_inventory.csv", index=False)

print("\n✅ REPORT GENERATED SUCCESSFULLY")