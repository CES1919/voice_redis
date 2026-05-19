#!/usr/bin/env python3
"""
ROS 节点示例：从 processed_events 读取 → 发布 ROS2 topic → ACK

如果 ROS2 环境不可用，会回退到 stdout 输出模式。

关键：ACK 顺序是「发布 → ACK」，
     确保消息成功发出后才确认。

用法:
    pip install redis
    # 如有 ROS2 环境:
    #   source /opt/ros/humble/setup.bash
    python redis_to_ros2_string.py

环境变量:
    REDIS_HOST         (默认 127.0.0.1)
    REDIS_PORT         (默认 6379)
    REDIS_USERNAME     (默认 ros2_reader)
    REDIS_PASSWORD     (默认 change_me_ros2)
    REDIS_STREAM_IN    (默认 processed_events)
    REDIS_GROUP_IN     (默认 ros2_consumers)
    REDIS_CONSUMER_NAME(默认 ros2-1)
    ROS_TOPIC          (默认 /voice_command)
    ROS_DOMAIN_ID      (默认 0)
"""

import json
import os
import sys

import redis


def get_redis_client() -> redis.Redis:
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        username=os.getenv("REDIS_USERNAME", "ros2_reader"),
        password=os.getenv("REDIS_PASSWORD", "change_me_ros2"),
        decode_responses=True,
    )


def try_import_rclpy():
    """尝试导入 rclpy，失败则返回 None"""
    try:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String
        return rclpy, Node, String
    except ImportError:
        return None, None, None


def main():
    client = get_redis_client()
    stream_in = os.getenv("REDIS_STREAM_IN", "processed_events")
    group_in = os.getenv("REDIS_GROUP_IN", "ros2_consumers")
    consumer = os.getenv("REDIS_CONSUMER_NAME", "ros2-1")
    ros_topic = os.getenv("ROS_TOPIC", "/voice_command")

    # Consumer Group 由 init 容器统一创建，无需手动创建

    # 尝试初始化 ROS2
    rclpy, Node, String = try_import_rclpy()
    ros_node = None
    publisher = None

    if rclpy is not None:
        try:
            rclpy.init()
            ros_node = Node("redis_to_ros2_bridge")
            publisher = ros_node.create_publisher(String, ros_topic, 10)
            print(f"ROS2 已初始化，发布到 {ros_topic}")
        except Exception as e:
            print(f"ROS2 初始化失败: {e}，回退到 stdout 模式")
            ros_node = None
    else:
        print("rclpy 未安装，使用 stdout 输出模式")

    print(f"消费者: {group_in}/{consumer}")
    print(f"读取: {stream_in}")
    print("等待消息...\n")

    try:
        while True:
            messages = client.xreadgroup(
                group_in, consumer, {stream_in: ">"}, count=10, block=5000
            )

            if not messages:
                # 让 rclpy 有机会处理回调
                if rclpy and ros_node:
                    rclpy.spin_once(ros_node, timeout_sec=0)
                continue

            for stream_name, entries in messages:
                for msg_id, fields in entries:
                    label = fields.get("label", "{}")
                    print(f"  收到: {msg_id} -> {json.dumps(fields, ensure_ascii=False)}")

                    # 1. 发布 ROS2 topic
                    if publisher is not None:
                        msg = String()
                        msg.data = label
                        publisher.publish(msg)
                        print(f"  发布到 {ros_topic}: {label}")
                    else:
                        print(f"  [stdout] {ros_topic}: {label}")

                    # 2. ACK
                    client.xack(stream_in, group_in, msg_id)
                    print(f"  已确认: {msg_id}\n")

    except KeyboardInterrupt:
        print("\n退出")
    finally:
        if rclpy and ros_node:
            ros_node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
