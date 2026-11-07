import {
  keepPreviousData,
  onlineManager,
  QueryClient,
  QueryObserver,
} from "@tanstack/query-core";

type History = { flow: string };

function deferredHistory() {
  let resolve!: (history: History) => void;
  const promise = new Promise<History>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function waitForState(predicate: () => boolean) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 2));
  }
  throw new Error("Query state did not settle");
}

test("build history distinguishes initial, background, cross-flow and paused reads", async () => {
  const wasOnline = onlineManager.isOnline();
  onlineManager.setOnline(true);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  client.mount();
  const options = (flow: string, queryFn: () => Promise<History>) => ({
    queryKey: ["builds", flow],
    queryFn,
    placeholderData: keepPreviousData,
    retry: false,
  });
  const first = deferredHistory();
  let active = first;
  const observer = new QueryObserver(client, options("first", () => active.promise));
  const unsubscribe = observer.subscribe(() => {});
  let paused: typeof observer | undefined;
  let unsubscribePaused: (() => void) | undefined;
  try {
    expect(observer.getCurrentResult()).toMatchObject({
      isLoading: true,
      isFetching: true,
      isPlaceholderData: false,
    });
    first.resolve({ flow: "first" });
    await waitForState(() => !observer.getCurrentResult().isFetching);

    active = deferredHistory();
    const refetch = observer.refetch();
    expect(observer.getCurrentResult()).toMatchObject({
      data: { flow: "first" },
      isLoading: false,
      isFetching: true,
      isPlaceholderData: false,
    });
    active.resolve({ flow: "first" });
    await refetch;

    const second = deferredHistory();
    observer.setOptions(options("second", () => second.promise));
    // keepPreviousData reports success even though this flow has no history yet.
    expect(observer.getCurrentResult()).toMatchObject({
      status: "success",
      data: { flow: "first" },
      isLoading: false,
      isFetching: true,
      isPlaceholderData: true,
    });
    second.resolve({ flow: "second" });
    await waitForState(() => !observer.getCurrentResult().isFetching);

    observer.setOptions(options("error", () => Promise.reject(new Error("read failed"))));
    await waitForState(() => observer.getCurrentResult().isError);
    expect(observer.getCurrentResult()).toMatchObject({
      isLoading: false,
      isFetching: false,
      isPlaceholderData: false,
    });

    onlineManager.setOnline(false);
    paused = new QueryObserver(client, options("paused", async () => ({ flow: "paused" })));
    unsubscribePaused = paused.subscribe(() => {});
    expect(paused.getCurrentResult()).toMatchObject({
      fetchStatus: "paused",
      isLoading: false,
      isFetching: false,
      isPlaceholderData: false,
    });
    observer.setOptions(options("paused-next", async () => ({ flow: "paused-next" })));
    expect(observer.getCurrentResult()).toMatchObject({
      fetchStatus: "paused",
      data: { flow: "second" },
      isLoading: false,
      isFetching: false,
      isPlaceholderData: true,
    });
  } finally {
    unsubscribePaused?.();
    paused?.destroy();
    unsubscribe();
    observer.destroy();
    client.unmount();
    client.clear();
    onlineManager.setOnline(wasOnline);
  }
});
