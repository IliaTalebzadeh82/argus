"""Small explicit adapters for workload export and Kafka publication."""

import argparse
import os
from pathlib import Path

from argus.events.kafka import FRAUD_TOPIC, KafkaFraudEventProducer
from argus.events.kafka_admin import ensure_fraud_topic
from argus.simulation.export import export_workload
from argus.simulation.playback import play_workload
from argus.simulation.spec import WorkloadSpec
from argus.simulation.workload import run_mixed_workload


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    publish = commands.add_parser("publish")
    for command in (export, publish):
        command.add_argument("--spec", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    publish.add_argument(
        "--bootstrap-servers", default=os.environ.get("ARGUS_KAFKA_BOOTSTRAP_SERVERS")
    )
    publish.add_argument(
        "--topic", default=os.environ.get("ARGUS_FRAUD_TOPIC", FRAUD_TOPIC)
    )
    pacing = publish.add_mutually_exclusive_group()
    pacing.add_argument("--unpaced", action="store_true")
    pacing.add_argument("--speedup", type=float)
    args = parser.parse_args()
    spec = WorkloadSpec.from_json(args.spec.read_text(encoding="utf-8"))
    result = run_mixed_workload(spec.simulation, spec.world, spec.traffic)
    if args.command == "export":
        path = export_workload(result, args.output)
        print(
            f"Exported {result.traffic_summary.logical_event_count} logical events "
            f"and {result.traffic_summary.delivery_count} deliveries to {path}"
        )
    else:
        if not args.bootstrap_servers:
            parser.error(
                "--bootstrap-servers or ARGUS_KAFKA_BOOTSTRAP_SERVERS is required"
            )
        ensure_fraud_topic(args.bootstrap_servers, topic=args.topic)
        report = play_workload(
            result,
            KafkaFraudEventProducer(args.bootstrap_servers, topic=args.topic),
            speedup=args.speedup,
        )
        print(
            f"Published {report.published_deliveries} deliveries to "
            f"{args.topic} ({report.mode})"
        )


if __name__ == "__main__":
    main()
