"""Separate template audio from bounded personal reference memory."""
import sqlalchemy as sa
from alembic import op

revision = '0043_template_audio'
down_revision = '0042_seedance_admin_tasks'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'template_audio_references',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('source_url', sa.Text(), nullable=False, unique=True),
        sa.Column('uploaded_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('original_filename', sa.String(255)),
        sa.Column('content_type', sa.String(255)),
        sa.Column('size_bytes', sa.BigInteger()),
        sa.Column('duration_ms', sa.BigInteger()),
        sa.Column('probe_status', sa.String(16)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ready', 'deleted')", name='ck_template_audio_status'),
    )
    # Include hidden templates and formerly pruned rows with trustworthy metadata.
    # This changes no personal reference and cannot invent missing probe results.
    op.execute("""
        INSERT INTO template_audio_references
            (id, source_url, uploaded_by, status, original_filename, content_type,
             size_bytes, duration_ms, probe_status)
        SELECT DISTINCT ON (r.source_url)
            r.id, r.source_url, r.user_id, 'ready', r.original_filename, r.content_type,
            r.size_bytes, r.duration_ms, r.probe_status
        FROM user_references r
        WHERE r.kind = 'audio' AND r.probe_status = 'ready' AND r.duration_ms > 0
          AND EXISTS (SELECT 1 FROM admin_trends t
              WHERE t.payload::jsonb @> jsonb_build_object('parameters',
                  jsonb_build_object('reference_audio_urls', jsonb_build_array(r.source_url))))
        ORDER BY r.source_url, r.created_at DESC
    """)


def downgrade():
    # Explicit downgrade loses durable metadata; retain schema for code-only rollback.
    op.drop_table('template_audio_references')
