from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import grpc
import psutil
import time

import ray
from ray.core.generated import node_manager_pb2
from ray.core.generated import node_manager_pb2_grpc
from ray.tests.utils import RayTestTimeoutException


def test_worker_stats(ray_start_regular):
    raylet = ray.nodes()[0]
    num_cpus = raylet["Resources"]["CPU"]
    raylet_address = "{}:{}".format(raylet["NodeManagerAddress"],
                                    ray.nodes()[0]["NodeManagerPort"])

    channel = grpc.insecure_channel(raylet_address)
    stub = node_manager_pb2_grpc.NodeManagerServiceStub(channel)
    reply = stub.GetNodeStats(node_manager_pb2.NodeStatsRequest())
    # Check that there is one connected driver.
    drivers = [worker for worker in reply.workers_stats if worker.is_driver]
    assert len(drivers) == 1
    assert os.getpid() == drivers[0].pid

    timeout_seconds = 20
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout_seconds:
            raise RayTestTimeoutException(
                "Timed out while waiting for worker processes")

        # Wait for the workers to start.
        if len(reply.workers_stats) < num_cpus + 1:
            time.sleep(1)
            reply = stub.GetNodeStats(node_manager_pb2.NodeStatsRequest())
            continue

        # Check that the rest of the processes are workers, 1 for each CPU.
        assert len(reply.workers_stats) == num_cpus + 1
        # Check that all processes are Python.
        pids = [worker.pid for worker in reply.workers_stats]
        processes = [
            p.info["name"] for p in psutil.process_iter(attrs=["pid", "name"])
            if p.info["pid"] in pids
        ]
        for process in processes:
            assert "python" in process or "ray" in process
        break
