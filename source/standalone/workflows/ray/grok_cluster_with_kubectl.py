# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

import subprocess
import re
import time
import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def get_pods(namespace='default'):
    cmd = ['kubectl', 'get', 'pods', '-n', namespace, '--no-headers']
    output = subprocess.check_output(cmd).decode()
    pods = []
    for line in output.strip().split('\n'):
        fields = line.split()
        pod_name = fields[0]
        status = fields[2]
        pods.append((pod_name, status))
    return pods

def get_clusters(pods, cluster_name_prefix):
    clusters = set()
    for pod_name, _ in pods:
        match = re.match(r'(' + re.escape(cluster_name_prefix) + r'-\d+)', pod_name)
        if match:
            clusters.add(match.group(1))
    return sorted(clusters)

def check_clusters_running(pods, clusters):
    clusters_running = True
    for cluster in clusters:
        cluster_pods = [p for p in pods if p[0].startswith(cluster)]
        total_pods = len(cluster_pods)
        running_pods = len([p for p in cluster_pods if p[1] == 'Running'])
        if running_pods != total_pods:
            clusters_running = False
            break
    return clusters_running

def get_ray_address(head_pod, namespace='default'):
    cmd = ['kubectl', 'logs', head_pod, '-c', 'ray-head', '-n', namespace]
    try:
        output = subprocess.check_output(cmd).decode()
    except subprocess.CalledProcessError:
        return None
    match = re.search(r"RAY_ADDRESS='([^']+)'", output)
    if match:
        return match.group(1)
    else:
        return None

def get_ray_status(head_pod, namespace='default'):
    cmd = ['kubectl', 'exec', head_pod, '-c', 'ray-head', '-n', namespace, '--', 'ray', 'status']
    try:
        output = subprocess.check_output(cmd).decode()
        return output
    except subprocess.CalledProcessError:
        return None

def parse_ray_status(ray_status):
    num_cpu = None
    num_gpu = None
    ram_gb = None

    lines = ray_status.split('\n')
    in_resources = False

    for line in lines:
        # Toggle when in resources section
        if 'Resources' in line:
            in_resources = True
            continue
        # Parse resource section
        if in_resources:
            cpu_match = re.match(r'\s*([0-9.]+)/([0-9.]+) CPU', line)
            if cpu_match:
                num_cpu = float(cpu_match.group(2))
            gpu_match = re.match(r'\s*([0-9.]+)/([0-9.]+) GPU', line)
            if gpu_match:
                num_gpu = float(gpu_match.group(2))
            ram_match = re.match(r'\s*0B/([0-9.]+)GiB memory', line)
            if ram_match:
                ram_gb = float(ram_match.group(1))

    return num_cpu, num_gpu, ram_gb

def count_worker_pods(pods, cluster):
    return sum(1 for pod_name, status in pods if pod_name.startswith(cluster + '-worker') and status == 'Running')

def process_cluster(cluster_info):
    cluster, pods, namespace = cluster_info
    # Find head pod
    head_pod = None
    for pod_name, status in pods:
        if pod_name.startswith(cluster + '-head'):
            head_pod = pod_name
            break
    if not head_pod:
        return f"Error: Could not find head pod for cluster {cluster}\n"

    # Get RAY_ADDRESS
    ray_address = get_ray_address(head_pod, namespace=namespace)
    if not ray_address:
        return f"Error: Could not find RAY_ADDRESS for cluster {cluster}\n"

    # Get ray status
    ray_status = get_ray_status(head_pod, namespace=namespace)
    if not ray_status:
        return f"Error: Could not get ray status for cluster {cluster}\n"

    # Parse ray status
    num_cpu, num_gpu, ram_gb = parse_ray_status(ray_status)

    # Count worker pods
    total_workers = count_worker_pods(pods, cluster)

    # Format output
    output_line = f"name: {cluster} address: {ray_address} num_cpu: {num_cpu} num_gpu: {num_gpu} ram_gb: {ram_gb} total_workers: {total_workers}\n"
    return output_line

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Process Ray clusters and save their specifications.")
    parser.add_argument('--cluster-prefix', 
                        default="isaac-lab-hyperparameter-tuner",
                        help="The prefix for the cluster names.")
    parser.add_argument('--output-file', 
                        default='~/.cluster_config', 
                        help="The file to save cluster specifications.")
    args = parser.parse_args()

    CLUSTER_NAME_PREFIX = args.cluster_prefix
    # Expand user directory for output file
    CLUSTER_SPEC_FILE = os.path.expanduser(args.output_file)

    # Get current namespace
    try:
        CURRENT_NAMESPACE = subprocess.check_output(['kubectl', 'config', 'view', '--minify', '--output', 'jsonpath={..namespace}']).decode().strip()
        if not CURRENT_NAMESPACE:
            CURRENT_NAMESPACE = 'default'
    except subprocess.CalledProcessError:
        CURRENT_NAMESPACE = 'default'
    print(f"Using namespace: {CURRENT_NAMESPACE}")

    # Get all pods
    pods = get_pods(namespace=CURRENT_NAMESPACE)

    # Get clusters
    clusters = get_clusters(pods, CLUSTER_NAME_PREFIX)
    if not clusters:
        print(f"No clusters found with prefix {CLUSTER_NAME_PREFIX}")
        return

    # Wait for clusters to be running
    while True:
        pods = get_pods(namespace=CURRENT_NAMESPACE)  # Refresh pods list inside loop
        if check_clusters_running(pods, clusters):
            break
        else:
            print("Waiting for all clusters to spin up...")
            time.sleep(5)

    # Prepare cluster info for parallel processing
    cluster_infos = []
    for cluster in clusters:
        cluster_pods = [p for p in pods if p[0].startswith(cluster)]
        cluster_infos.append((cluster, cluster_pods, CURRENT_NAMESPACE))

    # Use ThreadPoolExecutor to process clusters in parallel
    results = []
    results_lock = threading.Lock()  # Create a lock for thread-safe results collection

    with ThreadPoolExecutor() as executor:
        future_to_cluster = {executor.submit(process_cluster, info): info[0] for info in cluster_infos}
        for future in as_completed(future_to_cluster):
            cluster_name = future_to_cluster[future]
            try:
                result = future.result()
                with results_lock:
                    results.append(result)
            except Exception as exc:
                print(f"{cluster_name} generated an exception: {exc}")

    # Sort results alphabetically by cluster name
    results.sort()

    # Write sorted results to the output file
    with open(CLUSTER_SPEC_FILE, 'w') as f:
        for result in results:
            f.write(result)

    print(f"Cluster spec information saved to {CLUSTER_SPEC_FILE}")
    # Display the contents of the config file
    with open(CLUSTER_SPEC_FILE, 'r') as f:
        print(f.read())

if __name__ == "__main__":
    main()