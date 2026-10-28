// dashboard/src/pages/Agent/Skills/components/SkillHubDetailDrawer.tsx
import { useEffect, useState, type ReactNode } from "react";
import { Drawer, Button, Tag, Empty, Spin } from "antd";
import {
  CircleCheck,
  Download,
  Eye,
  LayoutGrid,
  RefreshCw,
  Star,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../../api/request";
import { apiErrorMessage } from "../../../../utils/apiError";
import { skillHubPreviewPath } from "./skillInstallTarget";
import Markdown from "../../../../components/Markdown/LazyMarkdown";

export interface SkillHubSkill {
  slug: string;
  name: string;
  description: string;
  version: string;
  // Optional rich fields returned by the rankings API (absent from search).
  description_zh?: string;
  downloads?: number;
  installs?: number;
  stars?: number;
  verified?: boolean;
  iconUrl?: string | null;
  category?: string;
  source?: string;
  labels?: Record<string, unknown> | null;
}

interface SkillHubDetailDrawerProps {
  open: boolean;
  skill: SkillHubSkill | null;
  onClose: () => void;
  onInstall: (skill: SkillHubSkill) => void;
  installing: boolean;
  isInstalled: boolean;
}

function requiresApiKey(skill: SkillHubSkill): boolean {
  const v = skill.labels?.["requires_api_key"];
  return v === true || v === "true";
}

function fmt(n?: number): string {
  if (typeof n !== "number") return "—";
  if (n >= 10000) return `${(n / 10000).toFixed(n >= 100000 ? 0 : 1)}w`;
  return n.toLocaleString();
}

function Stat({
  icon,
  value,
  label,
}: {
  icon: ReactNode;
  value: string;
  label: string;
}) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 4,
      }}
    >
      <div
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: "var(--fn-text-primary)",
          lineHeight: 1.2,
        }}
      >
        {value}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          fontSize: 12,
          color: "var(--fn-text-tertiary)",
        }}
      >
        {icon}
        {label}
      </div>
    </div>
  );
}

function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontSize: 12,
        fontWeight: 500,
        letterSpacing: 0.3,
        color: "var(--fn-text-tertiary)",
        marginBottom: 10,
      }}
    >
      {children}
    </div>
  );
}

/** Preview target for a hub skill: SkillHub slug or external bundle URL. */
function previewParams(skill: SkillHubSkill): {
  skillName?: string;
  bundleUrl?: string;
} {
  const raw = skill as SkillHubSkill & { source_url?: string };
  const source = String(skill.source ?? "");
  const bundleUrl = String(raw.source_url ?? "");
  if (source && source !== "skillhub" && bundleUrl) {
    return { bundleUrl };
  }
  return { skillName: skill.slug };
}

function SkillPreview({ skill }: { skill: SkillHubSkill }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!expanded || content !== null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    request<{ name: string; content: string }>(
      skillHubPreviewPath(previewParams(skill)),
    )
      .then((payload) => {
        if (!cancelled) setContent(payload?.content ?? "");
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            apiErrorMessage(
              err,
              t("skills.previewFailed", "Failed to load preview"),
              t,
            ),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [expanded, content, skill, t]);

  if (!expanded) {
    return (
      <Button
        size="small"
        icon={<Eye size={14} />}
        onClick={() => setExpanded(true)}
      >
        {t("skills.viewSkillContent", "View SKILL.md")}
      </Button>
    );
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
          gap: 8,
        }}
      >
        <FieldLabel>SKILL.md</FieldLabel>
        <Button
          size="small"
          type="text"
          icon={<Eye size={14} />}
          onClick={() => setExpanded(false)}
          style={{ color: "var(--fn-text-tertiary)" }}
        >
          {t("common.collapse", "Collapse")}
        </Button>
      </div>
      {loading ? (
        <div style={{ textAlign: "center", padding: "24px 0" }}>
          <Spin size="small" />
        </div>
      ) : error ? (
        <div style={{ color: "var(--fn-color-danger, #ff4d4f)", fontSize: 13 }}>
          {error}
        </div>
      ) : content ? (
        <div
          style={{
            maxHeight: 420,
            overflow: "auto",
            padding: "12px 16px",
            background: "var(--fn-bg-tertiary)",
            borderRadius: 8,
            fontSize: 13,
          }}
        >
          <Markdown content={content} />
        </div>
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("skills.noPreview", "No SKILL.md content")}
        />
      )}
    </div>
  );
}

export function SkillHubDetailDrawer({
  open,
  skill,
  onClose,
  onInstall,
  installing,
  isInstalled,
}: SkillHubDetailDrawerProps) {
  const { t } = useTranslation();

  if (!skill) return null;

  const desc = skill.description_zh || skill.description;
  const hasStats =
    typeof skill.downloads === "number" ||
    typeof skill.installs === "number" ||
    typeof skill.stars === "number";

  return (
    <Drawer
      placement="right"
      onClose={onClose}
      open={open}
      width={520}
      destroyOnHidden
      title={
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            minWidth: 0,
          }}
        >
          {skill.iconUrl ? (
            <img
              src={skill.iconUrl}
              alt=""
              style={{
                width: 36,
                height: 36,
                borderRadius: 9,
                objectFit: "cover",
                flexShrink: 0,
              }}
            />
          ) : (
            <span
              style={{
                width: 36,
                height: 36,
                borderRadius: 9,
                flexShrink: 0,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: "var(--fn-color-brand-bg, rgba(79,110,247,0.12))",
                color: "var(--fn-color-brand)",
                fontSize: 18,
              }}
            >
              <Zap size={18} fill="currentColor" />
            </span>
          )}
          <span
            style={{
              fontSize: 16,
              fontWeight: 600,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {skill.name}
          </span>
          {skill.verified && (
            <CircleCheck
              size={15}
              style={{ color: "var(--fn-text-brand)", flexShrink: 0 }}
            />
          )}
        </div>
      }
      styles={{ body: { padding: "20px 24px" } }}
      footer={
        <Button
          type={isInstalled ? "default" : "primary"}
          size="large"
          icon={isInstalled ? <RefreshCw size={14} /> : <Download size={14} />}
          loading={installing}
          disabled={installing}
          onClick={() => onInstall(skill)}
          style={{ width: "100%" }}
        >
          {installing
            ? t("skills.installing")
            : isInstalled
            ? t("skills.reinstall")
            : t("skills.install")}
        </Button>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        {/* Tags row: version + status + api-key + category + source */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            alignItems: "center",
          }}
        >
          <Tag bordered={false} style={{ background: "var(--fn-bg-tertiary)" }}>
            {t("skills.skillVersion")} {skill.version || "—"}
          </Tag>
          {isInstalled && <Tag color="green">{t("skills.installed")}</Tag>}
          {requiresApiKey(skill) && (
            <Tag color="orange">{t("skills.requiresApiKey")}</Tag>
          )}
          {skill.category && <Tag bordered={false}>{skill.category}</Tag>}
          {skill.source && (
            <Tag bordered={false} style={{ background: "var(--fn-bg-tertiary)" }}>
              {skill.source}
            </Tag>
          )}
        </div>

        {/* Stats card */}
        {hasStats && (
          <div
            style={{
              display: "flex",
              alignItems: "stretch",
              padding: "16px 8px",
              background: "var(--fn-bg-tertiary)",
              borderRadius: 12,
            }}
          >
            <Stat
              icon={<Download size={14} />}
              value={fmt(skill.downloads)}
              label={t("skills.downloads")}
            />
            <div
              style={{ width: 1, background: "var(--fn-card-border-normal)" }}
            />
            <Stat
              icon={<LayoutGrid size={14} fill="currentColor" />}
              value={fmt(skill.installs)}
              label={t("skills.installs")}
            />
            <div
              style={{ width: 1, background: "var(--fn-card-border-normal)" }}
            />
            <Stat
              icon={<Star size={14} fill="currentColor" />}
              value={fmt(skill.stars)}
              label={t("skills.stars")}
            />
          </div>
        )}

        {/* Description */}
        <div>
          <FieldLabel>{t("skills.skillDescription")}</FieldLabel>
          {desc ? (
            <div
              style={{
                fontSize: 14,
                lineHeight: 1.7,
                color: "var(--fn-text-primary)",
              }}
            >
              {desc}
            </div>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t("skills.noDescription")}
            />
          )}
        </div>

        {/* Pre-install SKILL.md preview */}
        <SkillPreview skill={skill} />

        {/* Slug */}
        <div>
          <FieldLabel>ID / Slug</FieldLabel>
          <div
            style={{
              fontSize: 13,
              fontFamily: "var(--fn-font-mono, monospace)",
              padding: "10px 14px",
              background: "var(--fn-bg-tertiary)",
              borderRadius: 8,
              wordBreak: "break-all",
              color: "var(--fn-text-secondary)",
            }}
          >
            {skill.slug}
          </div>
        </div>
      </div>
    </Drawer>
  );
}
