---
// SiteConfig.astro — Global site configuration
// Replace all placeholders with actual client data before launch

const SITE_CONFIG = {
  // Business Info
  businessName: 'Your Business Name',
  tagline: 'Your tagline or short description here',
  eyebrowText: 'Serving [City] since [Year]',
  
  // Hero Section
  headline: 'We Help [Target Audience] Achieve [Key Outcome]',
  subheadline: 'Professional [business type] services in [City]. Trusted by [X]+ happy customers.',
  primaryCTA: 'Get Free Consultation',
  secondaryCTA: 'View Our Services',
  
  // Services Section
  sectionHeadline: 'Our Services',
  sectionSubheadline: 'Comprehensive solutions tailored to your needs',
  
  // About Section
  aboutHeadline: 'About Our Business',
  aboutDescription: 'We are a dedicated team providing quality services...',
  aboutDescriptionExtra: 'Our commitment to excellence sets us apart...',
  yearsExperience: '10',
  highlight1: '100+ Happy Customers',
  highlight2: 'Professional Team',
  highlight3: 'Quality Guaranteed',
  highlight4: '24/7 Support',
  
  // Contact Section
  contactHeadline: 'Let\'s Work Together',
  contactSubheadline: 'Have a question or ready to get started? Reach out today!',
  formHeadline: 'Send Us a Message',
  address: '123 Business Street, City, State 123456',
  phone: '+91 XXXXX XXXXX',
  email: 'hello@yourbusiness.com',
  businessHours: 'Mon-Sat: 9:00 AM - 6:00 PM',
};
---

<script>
  // Make config available globally for Astro components
  (window as any).SITE_CONFIG = SITE_CONFIG;
</script>