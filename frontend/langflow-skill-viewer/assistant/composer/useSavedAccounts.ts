import { useEffect, useState } from "react";
import { AssistantFailure, assistantRequest } from "../api";
import type { SavedConnection } from "../models";

export default function useSavedAccounts({
  owner,
  locked,
  selected,
  chosenProvider,
  fail,
}: {
  owner?: string;
  locked: boolean;
  selected: string;
  chosenProvider: string;
  fail: (error: unknown) => void;
}) {
  const [accounts, setAccounts] = useState<SavedConnection[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [accountsOwner, setAccountsOwner] = useState<string>();
  const [account, setAccount] = useState<SavedConnection>();
  useEffect(() => {
    setAccounts([]);
    setAccountsOwner(undefined);
    setAccount(undefined);
    if (locked || !owner) {
      setAccountsLoading(false);
      return;
    }
    setAccountsLoading(true);
    let current = true;
    const load = () => {
      void assistantRequest<{ connections: SavedConnection[] }>("/connections")
        .then((result) => {
          if (current) {
            if (!Array.isArray(result.connections))
              throw new AssistantFailure("assistant_connection_unavailable");
            setAccounts(result.connections);
            setAccountsOwner(owner);
          }
        })
        .catch((failure) => {
          if (current) fail(failure);
        })
        .finally(() => {
          if (current) setAccountsLoading(false);
        });
    };
    load();
    window.addEventListener("focus", load);
    return () => {
      current = false;
      window.removeEventListener("focus", load);
    };
  }, [owner, locked, fail]);

  useEffect(() => {
    if (
      selected ||
      locked ||
      accountsLoading ||
      account ||
      !owner ||
      accountsOwner !== owner
    )
      return;
    const connected = accounts.filter(
      (item) =>
        item.provider === chosenProvider && item.lifecycle === "connected",
    );
    const available =
      connected.find((item) => item.auth_state === "ready") ??
      connected.find((item) => item.auth_state === "expired") ??
      connected.find(
        (item) =>
          item.provider === "opencode" &&
          item.method === "opencode_go_key" &&
          item.auth_state === "unavailable",
      );
    if (available) setAccount(available);
  }, [
    selected,
    locked,
    accountsLoading,
    account,
    accounts,
    chosenProvider,
    owner,
    accountsOwner,
  ]);

  return { accounts, accountsLoading, accountsOwner, account, setAccount };
}
