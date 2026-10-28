import { useState } from "react";
import {
  App,
  Button,
  Input,
  InputNumber,
  Modal,
  Space,
  Tag,
  Typography,
} from "antd";

import { knowledgeBasesApi } from "../../api/modules/knowledgeBases";
import { apiErrorMessage } from "../../utils/apiError";

const { Text } = Typography;

export interface RetrievalTestHit {
  kb_id: string;
  kb_name: string;
  doc_id: string;
  filename: string;
  ordinal: number;
  score: number;
  text: string;
}

interface RetrievalTestModalProps {
  open: boolean;
  kbId: string | null;
  kbName: string;
  extraKbIds?: string[];
  onClose: () => void;
}

/**
 * Retrieval test: run a query the way a chat turn would and show
 * the ranked chunks that would be injected as context.
 */
export default function RetrievalTestModal({
  open,
  kbId,
  kbName,
  extraKbIds = [],
  onClose,
}: RetrievalTestModalProps) {
  const { message } = App.useApp();
  const [query, setQuery] = useState("");
  const [k, setK] = useState<number | undefined>(undefined);
  const [running, setRunning] = useState(false);
  const [ran, setRan] = useState(false);
  const [hits, setHits] = useState<RetrievalTestHit[]>([]);
  const [coverage, setCoverage] = useState<Record<string, number>>({});

  const run = async () => {
    if (!kbId || !query.trim()) return;
    setRunning(true);
    try {
      const result = await knowledgeBasesApi.retrievalTest(kbId, {
        query: query.trim(),
        kb_ids: extraKbIds,
        k,
      });
      setHits(result.hits);
      setCoverage(result.base_coverage ?? {});
      setRan(true);
    } catch (error) {
      message.error(apiErrorMessage(error, "Retrieval test failed"));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Modal
      open={open}
      title={`Retrieval test — ${kbName}`}
      width={760}
      onCancel={onClose}
      footer={null}
    >
      <Space.Compact style={{ width: "100%", marginTop: 8 }}>
        <Input
          placeholder="Type a question to see which chunks would be retrieved…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onPressEnter={() => void run()}
          disabled={!kbId}
        />
        <InputNumber
          min={1}
          max={100}
          placeholder="k"
          style={{ width: 80 }}
          value={k}
          onChange={(value) => setK(value ?? undefined)}
        />
        <Button
          type="primary"
          loading={running}
          disabled={!kbId || !query.trim()}
          onClick={() => void run()}
        >
          Test
        </Button>
      </Space.Compact>

      {ran ? (
        <>
          <div style={{ margin: "12px 0 8px" }}>
            {Object.entries(coverage).map(([id, count]) => (
              <Tag key={id}>
                {id === kbId ? kbName : id}: {count} chunks
              </Tag>
            ))}
            {hits.length === 0 ? (
              <Text type="secondary">No matching chunks found.</Text>
            ) : null}
          </div>
          <div
            style={{
              display: "grid",
              gap: 12,
              maxHeight: 420,
              overflowY: "auto",
            }}
          >
            {hits.map((hit, index) => (
              <div
                key={`${hit.kb_id}:${hit.doc_id}:${hit.ordinal}:${index}`}
                style={{
                  border: "1px solid var(--fn-border-tertiary, #e5e5e5)",
                  borderRadius: 8,
                  padding: "8px 12px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginBottom: 4,
                  }}
                >
                  <Text strong style={{ fontSize: 12 }}>
                    #{index + 1} · {hit.filename} · chunk #{hit.ordinal + 1}
                  </Text>
                  <Tag color="blue">{hit.score.toFixed(4)}</Tag>
                </div>
                <Text
                  style={{
                    fontSize: 12,
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                >
                  {hit.text}
                </Text>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </Modal>
  );
}
