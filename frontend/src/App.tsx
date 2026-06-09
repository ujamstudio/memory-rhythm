import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";
import Home from "@/pages/home";
import Landing from "@/pages/landing";
import Survey from "@/pages/survey";
import Patient from "@/pages/patient";
import Caregiver from "@/pages/caregiver";

const queryClient = new QueryClient();

function Router() {
  return (
    <Switch>
      {/* Home selector */}
      <Route path="/" component={Home} />

      {/* Mobile — patient experience */}
      <Route path="/patient" component={Landing} />
      {/* STEP 1 초기 설문 (conversational onboarding) */}
      <Route path="/survey" component={Survey} />
      <Route path="/patient/session" component={Patient} />

      {/* PC — caregiver dashboard */}
      <Route path="/caregiver" component={Caregiver} />

      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
