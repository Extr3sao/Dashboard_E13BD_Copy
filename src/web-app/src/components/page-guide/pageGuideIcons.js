import { createElement } from 'react';
import {
  ArrowRightLeft,
  BookOpen,
  Boxes,
  CheckSquare,
  Clock3,
  Cpu,
  Database,
  FileText,
  GitBranch,
  History,
  Info,
  LayoutDashboard,
  Layers3,
  Link2,
  Mail,
  Network,
  PlayCircle,
  RefreshCcw,
  Route,
  Search,
  Settings2,
  ShieldAlert,
  Sparkles,
  SquareTerminal,
  Target,
  Wand2,
  Workflow,
  Zap,
} from 'lucide-react';

export const GUIDE_ICONS = {
  ArrowRightLeft,
  BookOpen,
  Boxes,
  CheckSquare,
  Clock3,
  Cpu,
  Database,
  FileText,
  GitBranch,
  History,
  Info,
  LayoutDashboard,
  Layers3,
  Link2,
  Mail,
  Network,
  PlayCircle,
  RefreshCcw,
  Route,
  Search,
  Settings2,
  ShieldAlert,
  Sparkles,
  SquareTerminal,
  Target,
  Wand2,
  Workflow,
  Zap,
};

export function resolveGuideIcon(iconKey) {
  if (!iconKey) return Info;
  return GUIDE_ICONS[iconKey] || Info;
}

export function GuideIcon({ icon, ...props }) {
  return createElement(resolveGuideIcon(icon), props);
}
