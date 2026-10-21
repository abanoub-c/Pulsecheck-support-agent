import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ArrowUpRight, CircleAlert, Headphones, LoaderCircle, MessageSquareText, RotateCcw, Send, ShieldCheck } from 'lucide-react';
import { ApiRequestError, getCustomerConversations, getThread, getThreadId, postChat, waitForAgentReady } from '../lib/api';
import { useApp } from '../lib/AppContext';
import type { ChatMessage, ConversationSummary, SseEvent, ThreadState, TraceStep } from '../lib/types';
import { PageIntro, StatusChip } from '../components/ui/Primitives';
import { ThemedSelect } from '../components/ui/ThemedSelect';
import { ThinkingTrace } from '../components/chat/ThinkingTrace';

const MAX_CHARS = 500;
const blankState: ThreadState = { category: null, pending_categories: [], confidence: null, clarify_attempts: 0, turn_count: 0, resolution_status: 'open', escalation_reason: null };
function readTraceStep(data: Record<string, unknown>): TraceStep {
  return { id: String(data.id ?? crypto.randomUUID()), at: String(data.at ?? new Date().toISOString()), node: String(data.node ?? 'agent'), kind: String(data.kind ?? 'step'), title: String(data.title ?? 'Agent step'), detail: data.detail };
}
function roleName(role: ChatMessage['role']) { return role === 'human' ? 'Human specialist' : role === 'user' ? 'You' : 'Pulsecheck Support'; }
function timeLabel(value: string) { return new Date(value).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); }

export default function ChatPage() {
  const { demoCustomers, selectedCustomerId, notify } = useApp();
  const customer = demoCustomers.find((item) => item.customer_id === selectedCustomerId);
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const requestedThreadParam = searchParams.get('thread');
  const requestedThread = requestedThreadParam && /^[A-Za-z0-9_-]{8,64}$/.test(requestedThreadParam)
    ? requestedThreadParam
    : null;
  const [threadId, setThreadId] = useState(() => requestedThread || getThreadId(selectedCustomerId));
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadState, setThreadState] = useState<ThreadState>(blankState);
  const [threadStatus, setThreadStatus] = useState<'open' | 'resolved' | 'escalated'>('open');
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [retryMessage, setRetryMessage] = useState('');
  const [waking, setWaking] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [threadLoading, setThreadLoading] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const retryMessageIdRef = useRef<string | null>(null);
  const lastSeenMessageCount = useRef(0);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('chat-route');
    return () => root.classList.remove('chat-route');
  }, []);

  const loadThread = useCallback(async (id: string, quiet = false) => {
    if (!quiet) setThreadLoading(true);
    try {
      const record = await getThread(id);
      setMessages(record.messages);
      setThreadState(record.state);
      setThreadStatus(record.status);
      lastSeenMessageCount.current = record.messages.length;
    } catch (error) {
      // A new chat gets a client-generated thread ID before the backend has created
      // that thread. The initial GET therefore returns 404, which means “empty chat.”
      if (!(error instanceof ApiRequestError && error.status === 404)) {
        if (!quiet) setErrorMessage(error instanceof Error ? error.message : 'Could not load conversation.');
      }
    } finally { if (!quiet) setThreadLoading(false); }
  }, []);

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const data = await getCustomerConversations(selectedCustomerId);
      setConversations(data.items);
    } catch {
      setConversations([]);
    } finally { setHistoryLoading(false); }
  }, [selectedCustomerId]);

  useEffect(() => { void refreshHistory(); }, [refreshHistory]);

  useEffect(() => {
    if (requestedThreadParam && !requestedThread) setSearchParams({}, { replace: true });
    let id = getThreadId(selectedCustomerId);
    if (requestedThread && (location.pathname === '/chat')) {
      id = requestedThread;
      sessionStorage.setItem(`pulsecheck-thread:${selectedCustomerId}`, requestedThread);
    }
    setThreadId(id); setMessages([]); setThreadState(blankState); setThreadStatus('open'); setSteps([]); setErrorMessage('');
    void loadThread(id);
  }, [selectedCustomerId, requestedThread, requestedThreadParam, location.pathname, loadThread, setSearchParams]);

  useEffect(() => {
    const onReset = () => {
      const id = getThreadId(selectedCustomerId);
      setThreadId(id); setMessages([]); setThreadState(blankState); setThreadStatus('open'); setSteps([]); setErrorMessage(''); setRetryMessage('');
      retryMessageIdRef.current = null;
      void refreshHistory();
      void loadThread(id);
    };
    window.addEventListener('pulsecheck:reset', onReset);
    return () => window.removeEventListener('pulsecheck:reset', onReset);
  }, [selectedCustomerId, loadThread, refreshHistory]);

  useEffect(() => {
    if (threadStatus !== 'escalated' || !threadId) return;
    const timer = window.setInterval(() => {
      void loadThread(threadId, true);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [threadStatus, threadId, loadThread]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, steps, streaming]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const startNewConversation = () => {
    const id = crypto.randomUUID();
    sessionStorage.setItem(`pulsecheck-thread:${selectedCustomerId}`, id);
    setSearchParams({}, { replace: true });
    setThreadId(id); setMessages([]); setThreadState(blankState); setThreadStatus('open'); setSteps([]); setErrorMessage(''); setRetryMessage('');
  };

  const sendMessage = async (raw: string, retry = false) => {
    const text = raw.trim();
    if (!text || text.length > MAX_CHARS || streaming || threadStatus === 'escalated') return;
    setErrorMessage(''); setRetryMessage(''); setWaking(false); setElapsed(0); setStreaming(true); setSteps([]);
    const started = new Date().toISOString();
    const messageId = retry ? retryMessageIdRef.current ?? crypto.randomUUID() : crypto.randomUUID();
    if (!retry) {
      retryMessageIdRef.current = messageId;
      const userMessage: ChatMessage = { id: messageId, role: 'user', content: text, at: started };
      setMessages((current) => [...current, userMessage]);
    }
    setInput('');
    const controller = new AbortController(); abortRef.current = controller;
    let finished = false;
    let agentError = false;
    const elapsedTimer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    const wakeTimer = window.setTimeout(() => setWaking(true), 3000);
    const hardTimeout = window.setTimeout(() => {
      controller.abort();
      setErrorMessage('The agent did not become ready within 90 seconds. Please retry.');
      setRetryMessage(text);
    }, 90_000);
    try {
      await waitForAgentReady(controller.signal);
      setWaking(false);
      await postChat({ thread_id: threadId, customer_id: selectedCustomerId, message_id: messageId, message: text }, (event: SseEvent) => {
        if (event.event === 'step') {
          const step = readTraceStep(event.data);
          setSteps((current) => [...current, step]);
        } else if (event.event === 'message') {
          const content = String(event.data.content ?? '');
          const role = event.data.role === 'human' ? 'human' : 'assistant';
          const traceSteps = [...steps];
          const message: ChatMessage = { id: crypto.randomUUID(), role, content, at: new Date().toISOString(), trace: role === 'assistant' ? { steps: traceSteps, toolCalls: [], state: threadState, startedAt: started, finishedAt: new Date().toISOString() } : undefined };
          setMessages((current) => [...current, message]);
          lastSeenMessageCount.current += 1;
        } else if (event.event === 'state') {
          setThreadState(event.data as unknown as ThreadState);
        } else if (event.event === 'escalated') {
          setThreadStatus('escalated');
          setThreadState((state) => ({ ...state, resolution_status: 'escalated', escalation_reason: String(event.data.reason ?? '') }));
        } else if (event.event === 'error') {
          agentError = true;
          setErrorMessage(String(event.data.message ?? 'The agent could not complete the request.'));
          if (event.data.retryable) setRetryMessage(text);
        } else if (event.event === 'done') {
          finished = true;
        }
      }, controller.signal);
      setWaking(false);
      await loadThread(threadId, true);
      if (!agentError) retryMessageIdRef.current = null;
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = error instanceof Error ? error.message : 'The message could not be sent.';
        setErrorMessage(message); setRetryMessage(text);
        notify(message, 'error');
      }
    } finally {
      window.clearInterval(elapsedTimer); window.clearTimeout(wakeTimer); window.clearTimeout(hardTimeout);
      setStreaming(false); setWaking(false); abortRef.current = null;
      void refreshHistory();
      if (!finished && controller.signal.aborted) setThreadStatus((state) => state === 'escalated' ? state : 'open');
    }
  };

  const openConversation = (id: string) => {
    sessionStorage.setItem(`pulsecheck-thread:${selectedCustomerId}`, id);
    setSearchParams({ thread: id });
  };

  const promptChips = useMemo(() => customer ? [customer.prompt, 'Can you connect me with a human specialist?', 'Please show me my current plan details.', 'Simulate a tool failure'] : [], [customer]);
  const onComposeKey = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void sendMessage(input); }
  };
  const statusTone = threadStatus === 'escalated' ? 'warning' : threadStatus === 'resolved' ? 'success' : 'neutral';

  return <section className="page-content chat-page">
    <PageIntro eyebrow="Workspace / Conversation" title="Chat" description={customer ? `A customer-side view for ${customer.company}.` : 'Customer support conversation demo.'} actions={<StatusChip tone={statusTone}>{threadStatus === 'escalated' ? 'Waiting for a human' : threadStatus === 'resolved' ? 'Resolved' : 'Open thread'}</StatusChip>} />
    <div className="chat-workspace">
      <div className="chat-history-toolbar">
        <label htmlFor="conversation-history">Conversation history</label>
        <ThemedSelect
          id="conversation-history"
          className="conversation-history-select"
          value={conversations.some((item) => item.thread_id === threadId) ? threadId : ''}
          disabled={historyLoading}
          onChange={(id) => id ? openConversation(id) : startNewConversation()}
          options={[
            { value: '', label: 'New conversation' },
            ...conversations.map((item) => ({
              value: item.thread_id,
              label: `${new Date(item.updated_at).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })} · ${item.status} · ${item.title}`,
            })),
          ]}
        />
        <button className="button button-secondary" type="button" onClick={startNewConversation}>New chat</button>
      </div>
      {threadLoading && messages.length === 0 && <div className="chat-loading"><LoaderCircle className="spin" size={18} /> Loading conversation…</div>}
      <div className="transcript" ref={transcriptRef} role="log" aria-live="polite" aria-label="Conversation transcript">
        {messages.length === 0 && !threadLoading && <div className="chat-empty">
          <span className="chat-empty-mark"><MessageSquareText size={21} /></span>
          <h2>How can we help?</h2>
          <p>Choose a starting point or write a message. The agent will show its handoffs and tool activity as it works.</p>
          <div className="prompt-chips">{promptChips.map((prompt, index) => <button className="prompt-chip" key={`${index}-${prompt}`} onClick={() => void sendMessage(prompt)}><span>{prompt}</span><ArrowUpRight aria-hidden="true" size={14} /></button>)}</div>
          <span className="sample-note"><ShieldCheck size={13} /> Demo conversation · sample data only</span>
        </div>}
        {messages.map((message) => <article key={message.id} className={`message-row message-${message.role}`}>
          {message.role !== 'user' && <span className={`message-avatar ${message.role === 'human' ? 'human-avatar' : ''}`}>{message.role === 'human' ? <Headphones size={15} /> : <ActivityMark />}</span>}
          <div className="message-body">
            {message.role === 'assistant' && <ThinkingTrace id={`trace-${message.id}`} steps={message.trace?.steps ?? []} tools={message.trace?.toolCalls ?? []} state={message.trace?.state ?? threadState} startedAt={message.trace?.startedAt} finishedAt={message.trace?.finishedAt} />}
            <div className={`message-bubble ${message.role === 'user' ? 'customer-bubble' : message.role === 'human' ? 'human-bubble' : 'agent-bubble'}`}>
              <div className="message-label">{roleName(message.role)}{message.role === 'human' && <span className="human-label">Human handoff</span>}</div>
              <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                table: ({ node: _node, ...props }) => <div className="markdown-table-wrap"><table {...props} /></div>,
              }}>{DOMPurify.sanitize(message.content)}</ReactMarkdown></div>
              <time className="message-time">{timeLabel(message.at)}</time>
            </div>
          </div>
        </article>)}
        {streaming && <div className="message-row message-assistant live-assistant"><span className="message-avatar"><ActivityMark /></span><div className="message-body"><ThinkingTrace id="live-trace" steps={steps} state={threadState} streaming /><div className="typing-indicator"><span /><span /><span />{waking ? <span className="wake-label">Waking up the agent · {elapsed}s</span> : <span className="wake-label">Working · {elapsed}s</span>}</div></div></div>}
        {threadStatus === 'escalated' && <div className="escalation-banner"><span className="escalation-icon"><Headphones size={17} /></span><div><strong>Passed to a human specialist</strong><p>{threadState.escalation_reason?.replaceAll('_', ' ') || 'A human specialist is reviewing this conversation.'} Your conversation will resume here.</p></div></div>}
        {errorMessage && <div className="chat-error" role="alert"><CircleAlert size={16} /><span>{errorMessage}</span>{retryMessage && <button className="text-button" onClick={() => void sendMessage(retryMessage, true)}><RotateCcw size={14} /> Retry</button>}</div>}
      </div>
      {threadStatus !== 'escalated' && <form className="composer" onSubmit={(event) => { event.preventDefault(); void sendMessage(input); }}>
        <label className="visually-hidden" htmlFor="chat-composer">Write a message</label>
        <textarea id="chat-composer" rows={2} value={input} maxLength={MAX_CHARS} onChange={(event) => setInput(event.target.value)} onKeyDown={onComposeKey} placeholder="Write a message…" disabled={streaming} />
        <div className="composer-footer"><span className={input.length >= MAX_CHARS ? 'char-count is-limit' : 'char-count'}>{input.length}/{MAX_CHARS} <span>· Enter to send, Shift+Enter for a new line</span></span><button className="send-button" type="submit" disabled={streaming || !input.trim()} aria-label="Send message">{streaming ? <LoaderCircle className="spin" size={17} /> : <Send size={16} />}<span>Send</span></button></div>
      </form>}
      {threadStatus === 'escalated' && <div className="composer-paused"><ShieldCheck size={15} /> Chat is paused until the human specialist replies.</div>}
      <div className="chat-footer-note"><span>Responses are simulated from sample data.</span><span>Thread <code>{threadId.slice(0, 8)}</code></span></div>
    </div>
  </section>;
}

function ActivityMark() { return <span className="assistant-mark" aria-hidden="true"><span /></span>; }
