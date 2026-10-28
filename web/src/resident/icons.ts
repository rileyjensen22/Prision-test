import {
  Briefcase,
  BookOpen,
  Crown,
  DoorOpen,
  FileText,
  GraduationCap,
  HeartPulse,
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
  chess: Crown,
  chess_human: Crown,
  reading_general: BookOpen,
  advanced_education: GraduationCap,
  basic_education: School,
  outdoor_rec: TreePine,
  legal_materials: Scale,
  grievances_appeals: FileText,
  health_requests: HeartPulse,
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
