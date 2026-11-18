import ReactDOM from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import GraphAgents from "@/modals/graphAgents/GraphAgents";
import "@/style/classes.css";
import "@/style/index.css";
import "@/App.css";
import "@/style/applies.css";

// Actual production component and retained API data. No app auto-login,
// mutation endpoints, replacement auth, invented events or inference.
document.documentElement.classList.add("dark");
ReactDOM.createRoot(document.getElementById("root")!).render(
  <MemoryRouter><TooltipProvider><div style={{height:"100vh"}}>
    <GraphAgents flowId="261e3372-8b8d-440f-bb3d-73fb785d5c2d" />
  </div></TooltipProvider></MemoryRouter>,
);
