import { PipecatAppBase } from "@pipecat-ai/voice-ui-kit";
import { TooltipProvider } from "@/components/ui/tooltip";
import Session from "./vox/Session";

export default function App() {
  return (
    <TooltipProvider>
      <PipecatAppBase
        transportType="smallwebrtc"
        // Same-origin signaling endpoint (surface doc §2); Vite dev proxies /api
        // to the live bot — see vite.config.ts.
        connectParams={{ webrtcUrl: "/api/offer" }}
        themeProps={{ defaultTheme: "dark" }}
      >
        {({ client, handleConnect, handleDisconnect, error }) =>
          !client ? (
            <div className="grid h-full place-items-center text-sm text-muted-foreground">
              starting client…
            </div>
          ) : (
            <Session
              error={error}
              onConnect={handleConnect}
              onDisconnect={handleDisconnect}
            />
          )
        }
      </PipecatAppBase>
    </TooltipProvider>
  );
}
