import { useCallback, useEffect, useRef, useState } from "react";
import ReconnectingWebSocket from "reconnecting-websocket";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "./useAuth";

export type ConnectionState = "connected" | "reconnecting" | "offline";

function wsUrl(path: string, token: string | null): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  const q = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${proto}//${host}${path}${q}`;
}

export function useWebSocket<T>(
  path: string,
  enabled = true,
  onMessage?: (data: T) => void
): { lastMessage: T | null; connectionState: ConnectionState } {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [lastMessage, setLastMessage] = useState<T | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>("offline");
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const handleReconnect = useCallback(() => {
    queryClient.invalidateQueries();
  }, [queryClient]);

  useEffect(() => {
    if (!enabled) {
      setConnectionState("offline");
      return;
    }
    const url = wsUrl(path, token);
    const ws = new ReconnectingWebSocket(url, [], {
      maxReconnectionDelay: 8000,
      minReconnectionDelay: 1000,
    });
    ws.onopen = () => {
      setConnectionState("connected");
      handleReconnect();
    };
    ws.onclose = () => setConnectionState("offline");
    ws.onerror = () => setConnectionState("reconnecting");
    ws.onmessage = (ev) => {
      try {
        const parsed = JSON.parse(ev.data) as T;
        setLastMessage(parsed);
        onMessageRef.current?.(parsed);
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, [path, token, enabled, handleReconnect]);

  return { lastMessage, connectionState };
}
