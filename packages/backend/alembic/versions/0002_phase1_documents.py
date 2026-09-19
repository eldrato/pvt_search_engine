"""Phase 1: Documents and Document Chunks Schema

Revision ID: 0002_phase1_documents
Revises: 0001_initial
Create Date: 2026-09-18 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0002_phase1_documents'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'documents',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('source_type', sa.String(length=64), nullable=False, default='upload'),
        sa.Column('file_path', sa.String(length=1024), nullable=True),
        sa.Column('mime_type', sa.String(length=128), nullable=False, default='text/plain'),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False, default=0),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('raw_content', sa.Text(), nullable=True),
        sa.Column('doc_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_documents_title', 'documents', ['title'])
    op.create_index('ix_documents_source_type', 'documents', ['source_type'])
    op.create_index('ix_documents_content_hash', 'documents', ['content_hash'], unique=True)
    op.create_index('ix_documents_created_at', 'documents', ['created_at'])

    op.create_table(
        'document_chunks',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('document_id', sa.String(length=36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False, default=0),
        sa.Column('chunk_hash', sa.String(length=64), nullable=False),
        sa.Column('location_meta', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_document_chunks_document_id', 'document_chunks', ['document_id'])
    op.create_index('idx_doc_chunks_doc_idx', 'document_chunks', ['document_id', 'chunk_index'])


def downgrade() -> None:
    op.drop_table('document_chunks')
    op.drop_table('documents')
