import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import AdminApp from "./AdminApp";
import AgentApp from "./PhaseTwoApp";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {window.location.pathname.startsWith("/admin") ? <AdminApp /> : <AgentApp />}
  </StrictMode>,
);
