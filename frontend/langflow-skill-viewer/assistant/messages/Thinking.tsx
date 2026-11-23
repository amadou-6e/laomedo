import "./Thinking.css";

export default function Thinking() {
  return (
    <p
      role="status"
      aria-label="Thinking"
      aria-live="polite"
      className="min-h-6 text-sm text-muted-foreground"
    >
      <span className="sr-only">Thinking</span>
      <span aria-hidden="true">
        {Array.from("Thinking").map((letter, index) => (
          <span
            key={index}
            className="laomedo-thinking-letter"
            style={{ animationDelay: `${index * 75}ms` }}
          >
            {letter}
          </span>
        ))}
      </span>
    </p>
  );
}
