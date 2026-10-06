import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import { ApiError } from "./api/client";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: false,
      // Don't hammer a backend that is down or answering 4xx.
      retry: (count, err) => !(err instanceof ApiError && (err.isNetworkError || err.status < 500)) && count < 2,
    },
  },
});

// Dev-only mock mode (`/?mock=1`): the sample data is tree-shaken from production builds.
const MockApp = import.meta.env.DEV ? lazy(() => import("./MockApp.tsx")) : null;
const useMock = MockApp !== null && new URLSearchParams(window.location.search).get("mock") === "1";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {useMock && MockApp ? (
        <Suspense fallback={null}>
          <MockApp />
        </Suspense>
      ) : (
        <App />
      )}
    </QueryClientProvider>
  </StrictMode>,
);
