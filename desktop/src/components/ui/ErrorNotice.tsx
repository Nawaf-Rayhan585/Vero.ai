import "./ErrorNotice.css";

export function ErrorNotice({ message }: { message: string }) {
  return (
    <p className="vero-error-notice" role="alert">
      {message}
    </p>
  );
}
