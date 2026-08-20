import { useEffect, useRef, useState } from 'react';
import { Badge, Button, Card, Input, Spinner } from '@/components/ui';
import { ai, type AIResponse } from '@/services/api';
import { useMissionStore } from '@/stores/missionStore';

/**
 * The assistant.
 *
 * Not a general chatbot: it answers from the platform's own knowledge corpus
 * and shows the sources it used. When the corpus has nothing relevant it says
 * so, and that refusal is a feature — an assistant that always produces an
 * answer is one you cannot trust when it matters.
 *
 * The configured provider is displayed. With no LLM credentials the server
 * falls back to an extractive provider that composes answers out of retrieved
 * passages rather than generating prose, and the interface should say that
 * plainly rather than implying more capability than is present.
 */

const SUGGESTIONS = [
  'Why do rockets have multiple stages?',
  'What is specific impulse and why does it matter?',
  'What is max-Q and why do vehicles throttle down?',
  'Why does a rocket pitch over instead of flying straight up?',
  'What is a delta-v budget?',
];

interface Turn {
  question: string;
  response: AIResponse | null;
  error: string | null;
}

export default function Assistant() {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);
  const [provider, setProvider] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const result = useMissionStore((s) => s.result);

  useEffect(() => {
    ai.provider()
      .then((info) => setProvider(info.selected_provider))
      .catch(() => setProvider(null));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns, pending]);

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || pending) return;

    setQuestion('');
    setPending(true);
    setTurns((current) => [...current, { question: trimmed, response: null, error: null }]);

    try {
      const response = await ai.ask(trimmed);
      setTurns((current) =>
        current.map((turn, i) => (i === current.length - 1 ? { ...turn, response } : turn)),
      );
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'The assistant could not answer.';
      setTurns((current) =>
        current.map((turn, i) => (i === current.length - 1 ? { ...turn, error: message } : turn)),
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-8 space-y-5">
      <header>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="font-display text-2xl font-semibold text-space-100">AI Assistant</h1>
          {provider && (
            <Badge variant={provider === 'extractive' ? 'warning' : 'cryo'} className="text-2xs">
              {provider}
            </Badge>
          )}
        </div>
        <p className="text-sm text-space-400">
          Answers come from the platform's knowledge corpus, with sources attached.
          {provider === 'extractive' && (
            <>
              {' '}
              <span className="text-severity-warning">
                No language model is configured on this server, so answers are composed from
                retrieved passages rather than written.
              </span>
            </>
          )}
        </p>
      </header>

      {result && (
        <Card className="border-accent-cyan/25">
          <p className="text-2xs text-space-400 leading-relaxed">
            You have a flight in Mission Control ({result.outcome}). For questions about that
            specific flight, the failure analysis there has the telemetry attached — this page
            answers from the knowledge corpus only.
          </p>
        </Card>
      )}

      {turns.length === 0 && (
        <div className="space-y-2">
          <p className="text-2xs text-space-500">Try one of these</p>
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => ask(suggestion)}
                className="px-2.5 py-1 rounded-md text-2xs border border-space-700 bg-space-800/40 text-space-400 hover:text-space-200 hover:border-space-600 transition-colors focus-ring text-left"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      <ol className="space-y-4">
        {turns.map((turn, i) => (
          <li key={i} className="space-y-2">
            <div className="flex justify-end">
              <p className="max-w-[85%] px-3 py-2 rounded-lg bg-accent-cyan/10 border border-accent-cyan/25 text-xs text-space-100">
                {turn.question}
              </p>
            </div>

            {turn.error ? (
              <Card className="border-severity-critical/30">
                <p className="text-2xs text-severity-critical">{turn.error}</p>
              </Card>
            ) : turn.response ? (
              <AnswerCard response={turn.response} onFollowUp={ask} />
            ) : (
              <Card className="flex items-center gap-3">
                <Spinner />
                <span className="text-2xs text-space-500">Retrieving and composing…</span>
              </Card>
            )}
          </li>
        ))}
      </ol>

      <div ref={endRef} />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="sticky bottom-4 flex gap-2"
      >
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about space, rockets, or engineering…"
          aria-label="Your question"
          className="flex-1"
        />
        <Button type="submit" loading={pending} disabled={!question.trim()}>
          Ask
        </Button>
      </form>
    </div>
  );
}

function AnswerCard({
  response,
  onFollowUp,
}: {
  response: AIResponse;
  onFollowUp: (question: string) => void;
}) {
  return (
    <Card className="space-y-3">
      <p className="text-xs text-space-200 leading-relaxed whitespace-pre-line">
        {response.answer}
      </p>

      <div className="flex flex-wrap items-center gap-3 text-2xs text-space-600">
        {response.confidence && <span>confidence: {response.confidence.toLowerCase()}</span>}
        {response.data_origin && <span>· origin: {response.data_origin.toLowerCase()}</span>}
      </div>

      {response.freshness_note && (
        <p className="text-2xs text-severity-warning leading-relaxed">{response.freshness_note}</p>
      )}

      {response.sources && response.sources.length > 0 && (
        <div className="border-t border-space-800 pt-2">
          <p className="text-2xs uppercase tracking-wider text-space-500 mb-1">Sources</p>
          <ul className="space-y-0.5">
            {response.sources.map((source, i) => (
              <li key={i} className="text-2xs text-space-500">
                {source.source_url ? (
                  <a
                    href={source.source_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-accent-cyan hover:underline"
                  >
                    {source.source_name}
                  </a>
                ) : (
                  source.source_name
                )}
                <span className="text-space-600"> · {source.source_type}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {response.suggested_questions && response.suggested_questions.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-space-800 pt-2">
          {response.suggested_questions.slice(0, 3).map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => onFollowUp(suggestion)}
              className="px-2 py-0.5 rounded text-2xs border border-space-700 text-space-400 hover:text-space-200 transition-colors focus-ring"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}
