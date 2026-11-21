"""Show the start-up log of the CineBook API server(s) - use when a server does not become healthy.

Run from the project folder (virtual environment active):
    python infra\\scripts\\server-log.py

It prints, for each server in the Auto Scaling group, its state, the load balancer's health verdict
and the "CINEBOOK START" lines from its console log. The console log appears a few minutes after boot.
"""
import sys

import boto3

REGION = "ap-south-1"
GROUP = "cinebook-api-asg"
TARGET_GROUP = "cinebook-api-tg"


def main() -> int:
    autoscaling = boto3.client("autoscaling", region_name=REGION)
    ec2 = boto3.client("ec2", region_name=REGION)
    elb = boto3.client("elbv2", region_name=REGION)
    groups = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[GROUP])["AutoScalingGroups"]
    instances = groups[0]["Instances"] if groups else []
    if not instances:
        print("No API server is running (the system is paused, or the server is still being launched).")
        return 1
    health = {}
    try:
        arn = elb.describe_target_groups(Names=[TARGET_GROUP])["TargetGroups"][0]["TargetGroupArn"]
        for item in elb.describe_target_health(TargetGroupArn=arn)["TargetHealthDescriptions"]:
            verdict = item["TargetHealth"]
            health[item["Target"]["Id"]] = verdict["State"] + (f" ({verdict.get('Description', '')})" if verdict.get("Description") else "")
    except Exception as error:                                    # the load balancer may not exist while paused
        print(f"(load balancer health not available: {error.__class__.__name__})")
    for instance in instances:
        instance_id = instance["InstanceId"]
        print(f"=== {instance_id}: {instance['LifecycleState']}, load balancer says: {health.get(instance_id, 'not registered')}")
        output = ec2.get_console_output(InstanceId=instance_id, Latest=True).get("Output", "")
        if not output:
            print("    console log not available yet - try again in two minutes")
            continue
        lines = output.encode("ascii", "replace").decode().splitlines()
        ours = [line for line in lines if "cinebook-start" in line or "CINEBOOK START" in line]
        for line in (ours or lines)[-45:]:
            print("    " + line[-200:])
        if not ours:
            print("    (no CINEBOOK START lines yet: the start-up script has not run or the log is not published yet)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
