interface PlaceholderPageProps {
  title: string;
  phase: number;
}

export function PlaceholderPage({ title, phase }: PlaceholderPageProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <h1 className="text-3xl font-bold text-slate-100 mb-4">{title}</h1>
      <p className="text-slate-400 text-lg">Coming in Phase {phase}</p>
    </div>
  );
}
