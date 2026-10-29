import { useId, useState, type ReactNode } from "react";

interface Props {
  accept: string;
  multiple?: boolean;
  files: File[];
  onChange: (files: File[]) => void;
  title: ReactNode;
  hint: ReactNode;
}

/** A large tap target for choosing files, which also accepts drag and drop on computers. */
export function FilePicker({ accept, multiple, files, onChange, title, hint }: Props) {
  const id = useId();
  const [dragging, setDragging] = useState(false);
  return (
    <label
      htmlFor={id}
      className={`drop${dragging ? " dragging" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const dropped = Array.from(e.dataTransfer.files);
        if (dropped.length) onChange(multiple ? dropped : dropped.slice(0, 1));
      }}
    >
      <input id={id} type="file" accept={accept} multiple={multiple}
             onChange={(e) => onChange(Array.from(e.target.files ?? []))} />
      {files.length ? (
        <>
          <strong>{files.length === 1 ? files[0].name : `${files.length} files chosen`}</strong>
          <span className="muted small">Tap to choose again</span>
        </>
      ) : (
        <>
          <strong>{title}</strong>
          <span className="muted small">{hint}</span>
        </>
      )}
    </label>
  );
}
