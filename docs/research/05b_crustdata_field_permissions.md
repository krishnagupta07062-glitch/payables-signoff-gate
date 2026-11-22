> Real people's names and profile URLs in this report are replaced with labels (Person A, B, ...). Company names are kept. Raw API responses are not in the repo.

### /agent/query — status enabled, base 0.012 cr, 100 rpm
- Enabled: (no field list; whole response)
- Disabled: none
- premium_fields: data_search=0.0005, data_enrich=0.05, contact_business_email=0.25, contact_personal_email=0.5, contact_phone=0.5

### /company/enrich — status enabled, base 2.0 cr, 5 rpm
- Enabled (556 paths) by group: basic_info(19), competitors(6), crustdata_company_id(1), employee_reviews(55), followers(9), funding(63), headcount(19), hiring(9), indexed_at(1), locations(7), market_intel(47), metadata(4), news(8), people(196), public_launches(59), revenue(10), reviews(8), seo(12), social_profiles(5), software_reviews(6), status(2), taxonomy(7), updated_at(1), web_traffic(2)
- Disabled: hiring.* (9); maps.* (51); social_posts.* (53); social_profiles.crunchbase, social_profiles.crunchbase.url, social_profiles.crunchbase.uuid; technographics.* (21)
- premium_fields: technographics=2.0, social_posts=5.0

### /company/identify — status enabled, base 0.2 cr, 5 rpm
- Enabled (21 paths) by group: basic_info(16), crustdata_company_id(1), social_profiles(4)
- Disabled: headcount, headcount.total; locations, locations.country, locations.headquarters

### /company/search — status enabled, base 0.03 cr, 5 rpm
- Enabled (138 paths) by group: basic_info(16), crustdata_company_id(1), followers(6), funding(9), headcount(13), hiring(34), locations(8), maps(11), metadata(4), revenue(9), social_profiles(5), software_reviews(6), taxonomy(16)
- Disabled: social_profiles.crunchbase, social_profiles.crunchbase.url, social_profiles.crunchbase.uuid
- premium_fields: taxonomy=0.1, followers=0.2, headcount=0.2, roles=0.2, funding=0.2, hiring=0.2, software_reviews=0.2, maps=0.2
- premium_filters: taxonomy=0.1, followers=0.2, headcount=0.2, roles=0.2, funding=0.2, hiring=0.2, software_reviews=0.2, technographics=1.0, maps=0.2

### /company/search/autocomplete — status enabled, base None cr, 300 rpm
- Enabled (3 paths) by group: suggestions(3)
- Disabled: none

### /job/search — status enabled, base 0.03 cr, 5 rpm
- Enabled (59 paths) by group: company(36), content(2), crustdata_job_id(1), job_details(10), location(7), metadata(3)
- Disabled: none

### /person/enrich — status enabled, base 1.0 cr, 5 rpm
- Enabled (285 paths) by group: basic_profile(23), contact(13), crustdata_person_id(1), dev_platform_profiles(73), education(18), experience(66), fit(1), honors(8), metadata(2), professional_network(17), profile_ranking(9), research_profiles(44), skills(2), social_handles(7), updated_at(1)
- Disabled: assessment.* (4); basic_profile.last_updated; certifications.* (8); contact.last_updated; education.last_updated, education.schools.last_updated; experience.* (6); professional_network.* (5); recently_changed_jobs; social_handles.professional_network_identifier.urn_url; social_posts.* (55)
- premium_fields: contact.business_emails=1.0, contact.personal_emails=2.0, contact.phone_numbers=2.0, dev_platform_profiles=1.0, social_posts=5.0, research_profiles=2.0

### /person/identify — status enabled, base 1.0 cr, 5 rpm
- Enabled (18 paths) by group: basic_profile(16), crustdata_person_id(1), updated_at(1)
- Disabled: none

### /person/search — status enabled, base 0.03 cr, 5 rpm
- Enabled (219 paths) by group: basic_profile(19), certifications(8), contact(4), crustdata_person_id(1), dev_platform_profiles(43), education(18), experience(63), fit(1), honors(8), metadata(2), professional_network(6), profile_ranking(4), research_profiles(33), skills(2), social_handles(7)
- Disabled: basic_profile.first_name, basic_profile.last_name; contact.last_updated; education.last_updated, education.schools.last_updated; experience.employment_details.current.last_updated, experience.employment_details.past.last_updated, experience.last_updated; professional_network.last_updated; social_handles.professional_network_identifier.urn_url; years_of_experience; years_of_experience_raw
- premium_fields: experience=0.1, education=0.1, honors=0.2, professional_network.connections=0.2, professional_network.followers=0.2, professional_network.open_to_cards=0.2, professional_network.languages=0.2, skills=0.1, certifications=0.2, professional_network.summary=0.2, dev_platform_profiles.repos=2.5, dev_platform_profiles=0.8, research_profiles=0.2
- premium_filters: experience=0.1, education=0.1, honors=0.2, professional_network.connections=0.2, professional_network.followers=0.2, professional_network.open_to_cards=0.2, professional_network.languages=0.2, skills=0.1, certifications=0.2, dev_platform_profiles.repos=2.5, dev_platform_profiles=0.8, research_profiles=0.2

### /person/search/autocomplete — status enabled, base None cr, 300 rpm
- Enabled (3 paths) by group: suggestions(3)
- Disabled: none

### /social_post/search — status enabled, base 0.5 cr, 100 rpm
- Enabled (120 paths) by group: actor(15), article(3), backend_urn(1), comments(26), content_types(1), date_posted(1), document(4), engagement(11), entity_urn(1), has_video(1), hashtags(1), hyperlinks(5), is_edited(1), mentions(3), metadata(4), parent_post_urn(1), poll(6), post_type(1), reactors(16), reposter(15), share_url(1), share_urn(1), text(1)
- Disabled: none

### /web/enrich/live — status enabled, base 1.0 cr, 10 rpm
- Enabled (5 paths) by group: content(1), success(1), timestamp(1), title(1), url(1)
- Disabled: none

### /web/search/live — status enabled, base 1.0 cr, 10 rpm
- Enabled (12 paths) by group: metadata(4), query(1), results(5), success(1), timestamp(1)
- Disabled: none
