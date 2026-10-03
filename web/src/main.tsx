import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "./vendor/nocturne.css";
import "./vendor/prototype.css";
import "./app.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";

const root = createRoot(document.getElementById("root") as HTMLElement);

async function start() {
  // The scenario preview exists only in development; production builds drop the import.
  if (import.meta.env.DEV && window.location.hash.startsWith("#/preview/")) {
    const { Preview } = await import("./dev/preview");
    root.render(<Preview name={window.location.hash.slice("#/preview/".length)} />);
    return;
  }
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void start();
