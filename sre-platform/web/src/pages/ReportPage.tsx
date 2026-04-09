import { useEffect, useState } from "react";
import { submitReport } from "../api";

function IconUpload() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ width: 28, height: 28 }}>
      <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" strokeLinecap="round" />
      <path d="M12 4v12M8 8l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconFile() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ width: 28, height: 28 }}>
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 2v6h6M8 13h8M8 17h5" strokeLinecap="round" />
    </svg>
  );
}

export default function ReportPage() {
  const [description, setDescription] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [logs, setLogs] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!image) { setPreview(null); return; }
    const url = URL.createObjectURL(image);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  function _handleImageChange(e: React.ChangeEvent<HTMLInputElement>) {
    setImage(e.target.files?.[0] ?? null);
  }

  function _handleLogsChange(e: React.ChangeEvent<HTMLInputElement>) {
    setLogs(e.target.files?.[0] ?? null);
  }

  function _clearImage() {
    setImage(null);
    setPreview(null);
  }

  function _clearLogs() {
    setLogs(null);
  }

  async function _handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!image) { setError("Please attach an image."); return; }
    setError("");
    setSuccess("");
    setLoading(true);
    try {
      const result = await submitReport(description, image, logs);
      setSuccess(`Report submitted — ID: ${result.report_id}`);
      setDescription("");
      setImage(null);
      setLogs(null);
    } catch {
      setError("Failed to submit report. Are you still logged in?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Incident Report</h1>
          <p className="page-subtitle">Submit a new incident report for triage</p>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 640 }}>
        <form onSubmit={_handleSubmit}>
          {/* Details */}
          <div className="card-section">
            <p className="card-section-title">Details</p>
            <div className="field">
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What happened? Include any relevant details, error messages, or affected services…"
                required
              />
            </div>
          </div>

          {/* Screenshot */}
          <div className="card-section">
            <p className="card-section-title">Screenshot</p>
            <div className="field" style={{ marginBottom: 0 }}>
              <label>Image attachment</label>
              {preview ? (
                <div className="image-preview-wrapper">
                  <img src={preview} alt="Preview" className="image-preview" />
                  <div className="image-preview-footer">
                    <span className="image-preview-name">📎 {image?.name}</span>
                    <button type="button" className="btn btn-danger" onClick={_clearImage}>
                      Remove
                    </button>
                  </div>
                </div>
              ) : (
                <label className="file-dropzone" htmlFor="image-upload">
                  <span className="file-dropzone-icon"><IconUpload /></span>
                  <span className="file-dropzone-text">Click to attach an image</span>
                  <span className="file-dropzone-hint">PNG, JPG, GIF up to 10 MB</span>
                  <input
                    id="image-upload"
                    type="file"
                    accept="image/*"
                    onChange={_handleImageChange}
                  />
                </label>
              )}
            </div>
          </div>

          {/* Logs */}
          <div className="card-section">
            <p className="card-section-title">Logs <span style={{ textTransform: "none", fontWeight: 400, color: "var(--text-muted)", letterSpacing: 0 }}>(optional)</span></p>
            <div className="field" style={{ marginBottom: 0 }}>
              <label>Log file</label>
              {logs ? (
                <div className="image-preview-footer" style={{ border: "1px solid var(--border-base)", borderRadius: "var(--radius-md)", background: "var(--bg-subtle)" }}>
                  <span className="image-preview-name">📄 {logs.name}</span>
                  <button type="button" className="btn btn-danger" onClick={_clearLogs}>
                    Remove
                  </button>
                </div>
              ) : (
                <label className="file-dropzone" htmlFor="logs-upload">
                  <span className="file-dropzone-icon"><IconFile /></span>
                  <span className="file-dropzone-text">Click to attach a log file</span>
                  <span className="file-dropzone-hint">.JSON, .LOG</span>
                  <input
                    id="logs-upload"
                    type="file"
                    accept=".json,.log,application/json,text/plain"
                    onChange={_handleLogsChange}
                  />
                </label>
              )}
            </div>
          </div>

          {error && <div className="feedback feedback-error">{error}</div>}
          {success && <div className="feedback feedback-success">{success}</div>}

          <div style={{ marginTop: "1.25rem", display: "flex", justifyContent: "flex-end" }}>
            <button type="submit" className="btn btn-primary" disabled={loading} style={{ height: 36, padding: "0 1.25rem", fontSize: "0.875rem" }}>
              {loading ? "Submitting…" : "Submit report"}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
