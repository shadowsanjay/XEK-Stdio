"""Initial schema for XEK STUDIO."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    op.create_table("projects", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("name", sa.String(200), nullable=False), sa.Column("spec", sa.JSON, nullable=False),
                    sa.Column("screenplay", sa.JSON), sa.Column("version", sa.Integer, nullable=False),
                    sa.Column("approved_version", sa.Integer), sa.Column("status", sa.String(40), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("script_versions", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("project_id", sa.String(36), nullable=False), sa.Column("version", sa.Integer, nullable=False),
                    sa.Column("screenplay", sa.JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_script_versions_project_id", "script_versions", ["project_id"])
    op.create_table("jobs", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("project_id", sa.String(36), nullable=False), sa.Column("kind", sa.String(40), nullable=False),
                    sa.Column("state", sa.String(40), nullable=False), sa.Column("stage", sa.String(100), nullable=False),
                    sa.Column("progress", sa.Integer, nullable=False), sa.Column("error", sa.Text),
                    sa.Column("logs", sa.JSON, nullable=False), sa.Column("payload", sa.JSON, nullable=False),
                    sa.Column("attempts", sa.Integer, nullable=False), sa.Column("cancel_requested", sa.Boolean, nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("run_at", sa.DateTime(timezone=True)))
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])
    op.create_table("assets", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("project_id", sa.String(36), nullable=False), sa.Column("kind", sa.String(30), nullable=False),
                    sa.Column("path", sa.Text, nullable=False), sa.Column("metadata_json", sa.JSON, nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_assets_project_id", "assets", ["project_id"])
    op.create_table("channels", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("name", sa.String(200), nullable=False), sa.Column("encrypted_tokens", sa.Text, nullable=False),
                    sa.Column("oauth_state", sa.String(200)))
    op.create_table("uploads", sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("asset_id", sa.String(36), nullable=False, unique=True),
                    sa.Column("project_id", sa.String(36), nullable=False), sa.Column("state", sa.String(50), nullable=False),
                    sa.Column("youtube_id", sa.String(100)), sa.Column("metadata_json", sa.JSON, nullable=False), sa.Column("error", sa.Text))
    op.create_index("ix_uploads_project_id", "uploads", ["project_id"])


def downgrade():
    for table in ["uploads", "channels", "assets", "jobs", "script_versions", "projects"]:
        op.drop_table(table)
