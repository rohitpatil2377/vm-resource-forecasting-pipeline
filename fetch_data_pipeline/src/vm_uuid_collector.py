import os
import json
import logging
import sys
import pika
import yaml
from pathlib import Path

# ============================================================
# PATH
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / "configs" / "vm_source.yaml"

# ============================================================
# RABBITMQ CONFIG
# ============================================================
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = 31023
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
QUEUE_NAME = "vm_config_sync"

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logging.getLogger("pika").setLevel(logging.WARNING)
logger = logging.getLogger("vm_uuid_collector")

# ============================================================
# YAML WRITER
# ============================================================
def write_yaml(vm_uuids: list):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "vm_source": {
            "mode": "static",
            "vm_list": vm_uuids,  # snapshot (can be empty)
        }
    }

    with open(OUTPUT_FILE, "w") as f:
        yaml.safe_dump(payload, f, sort_keys=False)

    logger.info("vm_source.yaml updated (VMs=%d)", len(vm_uuids))


# ============================================================
# MAIN
# ============================================================
def main():
    logger.info("Starting daily VM UUID snapshot collector")

    credentials = pika.PlainCredentials(
        RABBITMQ_USER,
        RABBITMQ_PASSWORD
    )

    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=60,
    )

    try:
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        logger.info("Connected to RabbitMQ queue: %s", QUEUE_NAME)
    except Exception as e:
        logger.critical("RabbitMQ connection failed: %s", e)
        sys.exit(1)

    # --------------------------------------------------
    # Read messages UNTIL valid snapshot found
    # --------------------------------------------------
    while True:
        method, properties, body = channel.basic_get(
            queue=QUEUE_NAME,
            auto_ack=True,
        )

        if body is None:
            logger.warning("No messages left in queue. YAML not updated.")
            break

        # ---------------- Decode safely ----------------
        try:
            body_str = body.decode("utf-8")
        except Exception:
            logger.warning("Non-decodable message skipped")
            continue

        # ---------------- Parse JSON ----------------
        try:
            packet = json.loads(body_str)
        except json.JSONDecodeError:
            logger.warning("Non-JSON message skipped: %s", body_str[:100])
            continue

        raw_vm_uuid = packet.get("vm_uuid")

        # ---------------- Validate ----------------
        if raw_vm_uuid is None:
            logger.warning("Message without vm_uuid skipped: %s", packet)
            continue

        if isinstance(raw_vm_uuid, list):
            vm_uuids = raw_vm_uuid
        elif isinstance(raw_vm_uuid, str):
            vm_uuids = [raw_vm_uuid]
        else:
            logger.warning("Invalid vm_uuid type skipped: %s", type(raw_vm_uuid))
            continue

        logger.info("Valid VM snapshot received (%d VMs)", len(vm_uuids))

        write_yaml(vm_uuids)
        break  # 🔥 STOP after first valid snapshot

    connection.close()
    logger.info("VM UUID collector finished")


# ============================================================
# ENTRYPOINT
# ============================================================
if __name__ == "__main__":
    main()
