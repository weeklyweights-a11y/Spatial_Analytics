import { useState, type KeyboardEvent } from "react";

interface SkillsInputProps {
  skills: string[];
  onChange: (skills: string[]) => void;
}

export function SkillsInput({ skills, onChange }: SkillsInputProps) {
  const [input, setInput] = useState("");

  const addSkill = () => {
    const trimmed = input.trim();
    if (trimmed && !skills.includes(trimmed)) {
      onChange([...skills, trimmed]);
    }
    setInput("");
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addSkill();
    }
  };

  return (
    <div>
      <label className="block text-sm text-slate-400 mb-1">Skills</label>
      <div className="flex flex-wrap gap-2 mb-2">
        {skills.map((s) => (
          <span key={s} className="px-2 py-1 bg-slate-800 rounded text-sm flex items-center gap-1">
            {s}
            <button type="button" onClick={() => onChange(skills.filter((x) => x !== s))} className="text-slate-500 hover:text-red-400">
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          className="flex-1 px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg"
          placeholder="Add skill and press Enter"
        />
        <button type="button" onClick={addSkill} className="px-3 py-2 bg-slate-700 rounded-lg text-sm">
          Add
        </button>
      </div>
    </div>
  );
}
