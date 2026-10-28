import {
  Briefcase,
  Brain,
  BookOpen,
  Crown,
  DoorOpen,
  FileText,
  GraduationCap,
  HeartPulse,
  Library,
  MessageSquare,
  Phone,
  PhoneCall,
  Scale,
  School,
  ShoppingBasket,
  Sprout,
  TreePine,
  Users,
  Video,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

/** One icon per feature. Always rendered next to the feature's name, never alone. */
export const FEATURE_ICON: Record<string, LucideIcon> = {
  calls: Phone,
  texting: MessageSquare,
  video: Video,
  commissary: ShoppingBasket,
  chess_engine: Crown,
  chess_human: Crown,
  reading_general: BookOpen,
  reading_expanded: Library,
  advanced_education: GraduationCap,
  basic_education: School,
  outdoor_rec: TreePine,
  legal_materials: Scale,
  grievances_appeals: FileText,
  medical_requests: HeartPulse,
  mental_health_requests: Brain,
  emergency_contact: PhoneCall,
  religious_texts: BookOpen,
  attorney_calls: Briefcase,
  contact_requests: Users,
  out_of_cell_minimum: DoorOpen,
  jobs: Wrench,
  reentry: Sprout,
}

export function featureIcon(name: string): LucideIcon {
  return FEATURE_ICON[name] ?? FileText
}
