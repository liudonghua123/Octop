import { useCallback, useEffect, useState } from "react";
import { App, Button, Input, Modal, Spin, Tag, Typography } from "antd";

import { knowledgeBasesApi } from "../../api/modules/knowledgeBases";
import { apiErrorMessage } from "../../utils/apiError";

const { TextArea } = Input;
const { Text } = Typography;

export interface KnowledgeChunk {
  ordinal: number;
  text: string;
  metadata: Record<string, unknown>;
}

interface DocumentChunksModalProps {
  open: boolean;
  kbId: string | null;
  documentId: string | null;
  filename: string;
  canWrite: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

/**
 * View and adjust how a document is segmented into index chunks.
 * Edits re-embed and replace the stored chunks without re-parsing
 * the original file.
 */
export default function DocumentChunksModal({
  open,
  kbId,
  documentId,
  filename,
  canWrite,
  onClose,
  onSaved,
}: DocumentChunksModalProps) {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [chunkCount, setChunkCount] = useState(0);
  const [texts, setTexts] = useState<string[]>([]);
  const [status, setStatus] = useState<string>("");

  const load = useCallback(async () => {
    if (!kbId || !documentId) return;
    setLoading(true);
    try {
      const payload = await knowledgeBasesApi.getDocumentChunks(
        kbId,
        documentId,
      );
      setChunkCount(payload.chunk_count);
      setTexts(payload.chunks.map((chunk) => chunk.text));
      setStatus(payload.status);
    } catch (error) {
      message.error(apiErrorMessage(error, "Failed to load document chunks"));
      onClose();
    } finally {
      setLoading(false);
    }
  }, [kbId, documentId, message, onClose]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const handleSave = async () => {
    if (!kbId || !documentId) return;
    setSaving(true);
    try {
      await knowledgeBasesApi.setDocumentChunks(kbId, documentId, texts);
      message.success("Chunks saved and re-embedded");
      onSaved?.();
      onClose();
    } catch (error) {
      message.error(apiErrorMessage(error, "Failed to save chunks"));
    } finally {
      setSaving(false);
    }
  };

  const dirty = texts.length > 0;

  return (
    <Modal
      open={open}
      title={
        <span>
          {filename} —{" "}
          <Text type="secondary" style={{ fontSize: 13 }}>
            {chunkCount} chunks
            {status ? ` · ${status}` : ""}
          </Text>
        </span>
      }
      width={720}
      onCancel={onClose}
      footer={
        canWrite
          ? [
              <Button key="cancel" onClick={onClose}>
                Cancel
              </Button>,
              <Button
                key="save"
                type="primary"
                loading={saving}
                disabled={loading || !dirty}
                onClick={() => void handleSave()}
              >
                Save & re-embed
              </Button>,
            ]
          : null
      }
    >
      {loading ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin />
        </div>
      ) : texts.length === 0 ? (
        <Text type="secondary">
          This document has no indexed chunks yet. Rebuild the index first.
        </Text>
      ) : (
        <div
          style={{
            display: "grid",
            gap: 12,
            maxHeight: 480,
            overflowY: "auto",
          }}
        >
          {texts.map((text, index) => (
            <div key={index}>
              <Tag style={{ marginBottom: 4 }}>#{index + 1}</Tag>
              <TextArea
                value={text}
                readOnly={!canWrite}
                autoSize={{ minRows: 3, maxRows: 10 }}
                onChange={(event) => {
                  const next = [...texts];
                  next[index] = event.target.value;
                  setTexts(next);
                }}
              />
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
