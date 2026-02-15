from app.core.enums import JobStatus
from app.db import crud
from app.db.session import SessionLocal
from app.workers.tasks import run_pipeline_batch_sync


def main() -> None:
    db = SessionLocal()
    try:
        user = crud.get_single_user(db)
        if not user:
            raise RuntimeError("No user found. Run scripts/seed.py first")

        print("Running fully automated pipeline for top 3 DISCOVERED jobs...")
        results = run_pipeline_batch_sync(
            top_n=3,
            status_filter=JobStatus.DISCOVERED.value,
            actor_id=str(user.id),
            manual_decision="AUTO_APPROVE",
            auto_packet=True,
        )
        successful = [
            state
            for state in results
            if state.get("status") in {JobStatus.PACKET_BUILT.value, JobStatus.SUBMITTED.value}
        ]
        blocked = [state for state in results if state.get("status") not in {JobStatus.PACKET_BUILT.value, JobStatus.SUBMITTED.value}]
        print(f"Pipeline processed {len(results)} jobs: success={len(successful)}, blocked={len(blocked)}")
        for state in successful:
            print(
                "Pipeline success:",
                f"job_id={state.get('job_id')}",
                f"application_id={state.get('application_id')}",
                f"status={state.get('status')}",
            )
        for state in blocked:
            print(
                "Blocked before packet build:",
                f"job_id={state.get('job_id')}",
                f"status={state.get('status')}",
                f"errors={state.get('errors')}",
            )
        print("Demo flow completed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
