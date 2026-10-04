// Renders a component inside the help context, with the tooltip, without the whole app.
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { HelpContext } from "../app/context";
import { HelpPopover, useHelpState } from "../components/HelpTip";

const noOverlay = () => () => {};

function WithHelp({ children }: { children: ReactNode }) {
  const ui = useHelpState(noOverlay);
  return (
    <HelpContext.Provider value={ui}>
      {children}
      <HelpPopover />
    </HelpContext.Provider>
  );
}

export const renderWithHelp = (node: ReactNode) => render(<WithHelp>{node}</WithHelp>);
